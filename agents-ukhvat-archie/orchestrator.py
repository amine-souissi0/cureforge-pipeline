"""
Main orchestrator.

Usage:
  python orchestrator.py          # daemon mode, polls every POLL_INTERVAL seconds
  python orchestrator.py --once   # run once and exit
  python orchestrator.py --test   # test all connections without processing posts
"""

import asyncio
import argparse
import time
from pathlib import Path
from datetime import datetime
from loguru import logger

from agents.telegram_monitor import TelegramMonitor
from agents.article_parser import ArticleParserAgent
from agents.dev_task_agent import DeveloperTaskAgent
from agents.sales_investor_agent import SalesInvestorAgent
from integrations.clickup_client import ClickUpClient
from integrations.outreach_bridge import queue_letters
from core.models import AgentResult, Department
from config.settings import get_settings

# Logging setup
Path("logs").mkdir(exist_ok=True)
logger.add("logs/pipeline.log", rotation="10 MB", retention="30 days", level="INFO")
logger.add("logs/errors.log", rotation="5 MB", retention="30 days", level="ERROR")


def save_letters(letters, post_id: int) -> None:
    out_dir = Path("outputs/letters")
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, letter in enumerate(letters):
        safe_org = letter.recipient_org[:40].replace(" ", "_").replace("/", "-")
        fname = out_dir / f"post{post_id}_{i+1}_{safe_org}.txt"
        content = (
            f"To: {letter.recipient_org}\n"
            f"Subject: {letter.subject}\n"
            f"Source: {letter.source_post_url}\n"
            f"\n{letter.body}"
        )
        fname.write_text(content, encoding="utf-8")
        logger.info(f"Letter saved: {fname}")


def process_one_post(post, parser, dev_agent, sales_agent, clickup) -> AgentResult:
    result = AgentResult(post_id=post.post_id)

    # 1. Parse article
    try:
        article = parser.parse(post)
        logger.info(
            f"Post {post.post_id} → '{article.title}' | depts: {[d.value for d in article.relevant_departments]}"
        )
    except Exception as e:
        logger.error(f"Parser crashed on post {post.post_id}: {e}")
        result.errors.append(f"parser: {e}")
        return result

    all_tasks = []

    # 2a. Developer tasks
    if Department.DEVELOPERS in article.relevant_departments:
        try:
            all_tasks.extend(dev_agent.generate_tasks(article))
        except Exception as e:
            logger.error(f"Dev agent error on post {post.post_id}: {e}")
            result.errors.append(f"dev_agent: {e}")

    # 2b. Sales / investor tasks + letters
    if Department.SALES in article.relevant_departments or article.is_investment_relevant:
        try:
            sales_tasks, letters = sales_agent.process(article)
            all_tasks.extend(sales_tasks)
            result.letters_drafted.extend(letters)
            if letters:
                save_letters(letters, post.post_id)
                queued, skipped = queue_letters(letters)
                logger.info(
                    f"Post {post.post_id}: outreach bridge queued={queued}, skipped={skipped}"
                )
        except Exception as e:
            logger.error(f"Sales agent error on post {post.post_id}: {e}")
            result.errors.append(f"sales_agent: {e}")

    # 2c. Other department task (generic fallback)
    if Department.OTHER in article.relevant_departments and article.other_notes:
        from core.models import ClickUpTask
        all_tasks.append(ClickUpTask(
            name=f"[Other] {article.title[:70]}",
            description=article.other_notes + f"\n\nSource: {article.source_url}",
            department=Department.OTHER,
            priority=3,
            tags=article.topics[:5],
            source_post_url=article.source_url,
        ))

    # 3. Push all tasks to ClickUp
    if all_tasks:
        try:
            created = clickup.create_tasks_batch(all_tasks)
            result.tasks_created.extend(created)
            logger.info(
                f"Post {post.post_id}: {len(created)}/{len(all_tasks)} ClickUp tasks created"
            )
        except Exception as e:
            logger.error(f"ClickUp batch failed for post {post.post_id}: {e}")
            result.errors.append(f"clickup: {e}")

    return result


def build_summary_message(results: list[AgentResult], elapsed: float) -> str:
    total_tasks = sum(len(r.tasks_created) for r in results)
    total_letters = sum(len(r.letters_drafted) for r in results)
    total_errors = sum(len(r.errors) for r in results)

    lines = [
        f"✅ <b>Pipeline run complete</b>",
        f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} ({elapsed:.0f}s)",
        f"📰 Posts processed: <b>{len(results)}</b>",
        f"📋 ClickUp tasks created: <b>{total_tasks}</b>",
        f"📧 Letters drafted: <b>{total_letters}</b>",
    ]
    if total_errors:
        lines.append(f"⚠️ Errors: {total_errors} (see logs/errors.log)")
    return "\n".join(lines)


def run_once(monitor: TelegramMonitor, parser, dev_agent, sales_agent, clickup) -> None:
    start = time.time()
    posts = monitor.get_new_posts()

    if not posts:
        logger.info("No new posts.")
        return

    monitor.send_message(f"🔍 Processing {len(posts)} new longevity post(s)...")

    results = []
    for post in posts:
        result = process_one_post(post, parser, dev_agent, sales_agent, clickup)
        results.append(result)

    elapsed = time.time() - start
    summary = build_summary_message(results, elapsed)
    logger.info(summary.replace("<b>", "").replace("</b>", ""))
    monitor.send_message(summary)


def test_connections() -> None:
    """Verify all services are reachable."""
    print("\n── Connection tests ──────────────────────")
    s = get_settings()

    # Groq
    try:
        from core.llm import LLMClient
        llm = LLMClient()
        result = llm.call("You are helpful.", "Say 'Groq OK'", max_tokens=10)
        print(f"✅ Groq: {result.strip()}")
    except Exception as e:
        print(f"❌ Groq: {e}")

    # ClickUp
    clickup = ClickUpClient()
    ok = clickup.verify_connection()
    print(f"{'✅' if ok else '❌'} ClickUp")

    # Telegram bot
    try:
        import requests
        r = requests.get(
            f"https://api.telegram.org/bot{s.telegram_bot_token}/getMe",
            timeout=10
        )
        bot_name = r.json().get("result", {}).get("username", "unknown")
        print(f"✅ Telegram bot: @{bot_name}")
    except Exception as e:
        print(f"❌ Telegram bot: {e}")

    print("──────────────────────────────────────────\n")


def main():
    ap = argparse.ArgumentParser(description="Longevity multi-agent pipeline")
    ap.add_argument("--once", action="store_true", help="Run once and exit")
    ap.add_argument("--test", action="store_true", help="Test connections and exit")
    args = ap.parse_args()

    if args.test:
        test_connections()
        return

    s = get_settings()

    # Init all components once
    monitor = TelegramMonitor()
    clickup = ClickUpClient()

    if not clickup.verify_connection():
        logger.error("ClickUp connection failed — check your API token in .env")
        return

    parser = ArticleParserAgent()
    dev_agent = DeveloperTaskAgent()
    sales_agent = SalesInvestorAgent()

    if args.once:
        run_once(monitor, parser, dev_agent, sales_agent, clickup)
    else:
        logger.info(f"Daemon started — polling every {s.poll_interval}s")
        monitor.send_message("🤖 <b>Longevity agent pipeline started</b>\nMonitoring @UkhvatNews...")
        while True:
            try:
                run_once(monitor, parser, dev_agent, sales_agent, clickup)
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
            logger.info(f"Sleeping {s.poll_interval}s...")
            time.sleep(s.poll_interval)


if __name__ == "__main__":
    main()
