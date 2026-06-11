"""
Telegram Signal Ingestion Agent — "Rachel's solution"

Reads messages from a Telegram channel (e.g. a news/signal feed),
uses Groq to classify and decompose each message into:

  - TECH_TASK    → creates a ClickUp task automatically
  - INVESTOR     → adds firm/email to the outreach pipeline
  - IGNORE       → skip (noise, ads, irrelevant)

This closes the loop:
  Telegram news → AI classification → ClickUp task OR investor outreach

Setup:
  Set BOT_TOKEN + SOURCE_CHANNEL_ID in .env
  Run: python agents/telegram_signal_agent.py
  Or call: process_new_messages() from the pipeline runner
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings

logger = logging.getLogger(__name__)

CLICKUP_TOKEN   = "pk_276748223_WVI8HANZXTLX18L3O3JNP9HCZ61Y4FSN"
CLICKUP_LIST_ID = "901317681503"   # update with actual list ID if needed

# ── Groq classification ───────────────────────────────────────────────────────

_CLASSIFY_SYSTEM = """\
You are an AI assistant for CureForge / LongevityInTime — a longevity biotech AI company.

You receive a Telegram message (news article summary, post, or signal).
Classify it into ONE category and extract structured data.

Categories:
- TECH_TASK     : mentions a new AI tool, model, API, research finding, competitor move, or
                  anything that requires engineering action or investigation
- INVESTOR      : mentions a VC fund, investor, accelerator, grant program, or funding opportunity
                  that CureForge should reach out to
- IGNORE        : ads, spam, irrelevant news, or anything unrelated to longevity/AI/biotech

Respond in JSON:
{
  "category": "TECH_TASK" | "INVESTOR" | "IGNORE",
  "title": "short title (max 10 words)",
  "summary": "1-2 sentence summary of why this is relevant",
  "action": "specific next step (what to do with this)",
  "firm_name": "investor/fund name if INVESTOR, else null",
  "firm_url": "investor website if detectable, else null",
  "priority": "high" | "normal" | "low"
}"""


def _classify(text: str) -> dict:
    """Use Groq to classify a Telegram message."""
    body = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": _CLASSIFY_SYSTEM},
            {"role": "user",   "content": text[:2000]},
        ],
        "max_tokens": 300,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }).encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type":  "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        result = json.loads(r.read())
        return json.loads(result["choices"][0]["message"]["content"])


# ── ClickUp task creation ─────────────────────────────────────────────────────

def _create_clickup_task(title: str, description: str, priority: str = "normal") -> str | None:
    """Create a ClickUp task and return its URL."""
    priority_map = {"high": 2, "normal": 3, "low": 4}
    data = json.dumps({
        "name":        title,
        "description": description,
        "priority":    priority_map.get(priority, 3),
        "tags":        ["telegram-signal", "auto-created"],
    }).encode()

    req = urllib.request.Request(
        f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID}/task",
        data=data,
        headers={
            "Authorization": CLICKUP_TOKEN,
            "Content-Type":  "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
            url  = resp.get("url", "")
            logger.info("ClickUp task created: %s", url)
            return url
    except Exception as e:
        logger.error("ClickUp task creation failed: %s", e)
        return None


# ── Add investor to outreach pipeline ────────────────────────────────────────

def _add_investor(firm_name: str, firm_url: str | None, summary: str) -> bool:
    """Add a newly discovered investor to the outreach DB."""
    from models.database import OutreachRecord, SessionLocal, init_db
    init_db()

    # Build a placeholder email from domain if URL available
    email = None
    if firm_url:
        try:
            domain = urllib.parse.urlparse(firm_url).netloc.lstrip("www.")
            email  = f"info@{domain}"
        except Exception:
            pass

    if not email:
        # Skip — can't email without an address
        logger.info("Skipping investor %s — no email extractable from %s", firm_name, firm_url)
        return False

    db = SessionLocal()
    try:
        existing = db.query(OutreachRecord).filter_by(email=email).first()
        if existing:
            logger.info("Investor %s already in pipeline", firm_name)
            return False
        record = OutreachRecord(
            name            = firm_name,
            email           = email,
            firm            = firm_name,
            focus_area      = "longevity / biotech VC",
            pipeline_status = "queued",
            drafted_subject = None,
            source_post_url = firm_url,
        )
        db.add(record)
        db.commit()
        logger.info("Added investor %s (%s) to pipeline", firm_name, email)
        return True
    finally:
        db.close()


# ── Telegram polling ──────────────────────────────────────────────────────────

def _tg_get_updates(bot_token: str, offset: int = 0) -> list[dict]:
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={offset}&timeout=10"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
            return data.get("result", [])
    except Exception as e:
        logger.error("Telegram getUpdates failed: %s", e)
        return []


def _tg_send(bot_token: str, chat_id: str | int, text: str) -> None:
    body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req  = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        logger.error("Telegram send failed: %s", e)


# ── Main processor ────────────────────────────────────────────────────────────

def process_message(text: str, bot_token: str | None = None, chat_id: str | int | None = None) -> dict:
    """
    Classify one message and take action.
    Returns the classification result dict.
    """
    result = _classify(text)
    category = result.get("category", "IGNORE")
    title    = result.get("title", "Signal")
    summary  = result.get("summary", "")
    action   = result.get("action", "")
    priority = result.get("priority", "normal")

    task_url = None

    if category == "TECH_TASK":
        description = (
            f"**Source:** Telegram signal\n\n"
            f"**Summary:** {summary}\n\n"
            f"**Action:** {action}\n\n"
            f"**Original message:**\n{text[:800]}"
        )
        task_url = _create_clickup_task(title, description, priority)
        logger.info("TECH_TASK created in ClickUp: %s", title)

    elif category == "INVESTOR":
        firm_name = result.get("firm_name") or title
        firm_url  = result.get("firm_url")
        _add_investor(firm_name, firm_url, summary)
        logger.info("INVESTOR added to pipeline: %s", firm_name)

    else:
        logger.debug("IGNORE: %s", title)

    # Notify via Telegram if bot configured
    if bot_token and chat_id and category != "IGNORE":
        emoji = "🔧" if category == "TECH_TASK" else "💰"
        notify = (
            f"{emoji} <b>[{category}]</b> {title}\n"
            f"{summary}\n"
        )
        if task_url:
            notify += f"<a href='{task_url}'>ClickUp task →</a>"
        _tg_send(bot_token, chat_id, notify)

    result["task_url"] = task_url
    return result


def run_poll_loop(bot_token: str, source_chat_id: int, notify_chat_id: int, state_file: str = "/tmp/tg_signal_offset.txt") -> None:
    """
    Poll the bot for new messages from source_chat_id, process each one.
    Runs forever (call from a background thread or separate process).
    """
    import time
    try:
        offset = int(Path(state_file).read_text())
    except Exception:
        offset = 0

    logger.info("Starting Telegram signal poll loop (offset=%d)", offset)
    while True:
        updates = _tg_get_updates(bot_token, offset)
        for update in updates:
            offset = update["update_id"] + 1
            Path(state_file).write_text(str(offset))

            msg = update.get("message") or update.get("channel_post")
            if not msg:
                continue
            chat_id  = msg.get("chat", {}).get("id")
            text     = msg.get("text") or msg.get("caption") or ""
            if not text or chat_id != source_chat_id:
                continue

            try:
                process_message(text, bot_token=bot_token, chat_id=notify_chat_id)
            except Exception as e:
                logger.error("process_message error: %s", e)

        time.sleep(3)


if __name__ == "__main__":
    import os
    bot_token       = os.getenv("TELEGRAM_BOT_TOKEN", "")
    source_chat_id  = int(os.getenv("TELEGRAM_SOURCE_CHANNEL_ID", "0"))
    notify_chat_id  = int(os.getenv("TELEGRAM_NOTIFY_CHANNEL_ID", "0"))

    if not bot_token or not source_chat_id:
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_SOURCE_CHANNEL_ID in .env")
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)
    run_poll_loop(bot_token, source_chat_id, notify_chat_id)
