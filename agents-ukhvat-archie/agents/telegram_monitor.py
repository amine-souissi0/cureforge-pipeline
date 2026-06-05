"""
Telegram channel monitor.

How it works:
- You forward posts from @UkhvatNews to @Longevity_recruit_bot
- The bot reads them via getUpdates and processes them
- No admin rights needed, no scraping
"""

import json
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta
from loguru import logger

from core.models import TelegramPost
from config.settings import get_settings

STATE_FILE = Path("logs/telegram_state.json")


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_update_id": 0, "last_post_ids": []}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


class TelegramMonitor:

    def __init__(self):
        s = get_settings()
        self.token = s.telegram_bot_token
        self.channel = s.telegram_channel
        self.user_id = s.telegram_user_id
        self.lookback_hours = s.lookback_hours
        self.base = f"https://api.telegram.org/bot{self.token}"

    def _get(self, method: str, params: dict = None) -> dict:
        r = requests.get(f"{self.base}/{method}", params=params or {}, timeout=15)
        r.raise_for_status()
        return r.json()

    def _post_api(self, method: str, data: dict) -> dict:
        r = requests.post(f"{self.base}/{method}", json=data, timeout=15)
        r.raise_for_status()
        return r.json()

    def send_message(self, text: str) -> None:
        try:
            self._post_api("sendMessage", {
                "chat_id": self.user_id,
                "text": text,
                "parse_mode": "HTML",
            })
        except Exception as e:
            logger.warning(f"Could not send status message: {e}")

    def get_new_posts(self) -> list[TelegramPost]:
        state = _load_state()
        seen_ids = set(state.get("last_post_ids", []))

        try:
            data = self._get("getUpdates", {
                "offset": state.get("last_update_id", 0) + 1,
                "limit": 100,
                "timeout": 0,
            })
        except Exception as e:
            logger.error(f"getUpdates failed: {e}")
            return []

        if not data.get("ok") or not data.get("result"):
            logger.info("No new updates from bot. Forward posts from @UkhvatNews to @Longevity_recruit_bot")
            return []

        posts = []
        max_update_id = state.get("last_update_id", 0)

        for update in data["result"]:
            max_update_id = max(max_update_id, update["update_id"])

            msg = update.get("message") or update.get("channel_post") or {}
            if not msg:
                continue

            text = msg.get("text", "") or msg.get("caption", "")
            if not text or len(text) < 20:
                continue

            # Skip the /start command message
            if text.strip() == "/start":
                continue

            msg_id = msg.get("message_id", 0)
            date_ts = msg.get("date", 0)

            # For forwarded messages, use forward date if available
            forward_origin = msg.get("forward_origin", {})
            fwd_date = (
                forward_origin.get("date")
                or msg.get("forward_date")
                or date_ts
            )
            posted_at = datetime.fromtimestamp(fwd_date, tz=timezone.utc)

            # Build source URL
            fwd_chat = msg.get("forward_from_chat", {})
            fwd_msg_id = msg.get("forward_from_message_id", 0)
            orig_username = fwd_chat.get("username", self.channel)
            if fwd_chat and fwd_msg_id:
                source_url = f"https://t.me/{orig_username}/{fwd_msg_id}"
                post_id = fwd_msg_id
            else:
                source_url = f"https://t.me/{self.channel}/{msg_id}"
                post_id = msg_id

            if post_id in seen_ids:
                continue

            posts.append(TelegramPost(
                post_id=post_id,
                text=text,
                url=source_url,
                posted_at=posted_at,
                channel=orig_username or self.channel,
            ))
            seen_ids.add(post_id)
            logger.info(f"New post: id={post_id} chars={len(text)} from={source_url}")

        state["last_update_id"] = max_update_id
        state["last_post_ids"] = list(seen_ids)[-200:]
        _save_state(state)

        if posts:
            logger.info(f"Fetched {len(posts)} new posts")
        else:
            logger.info("No new posts — forward more from @UkhvatNews to @Longevity_recruit_bot")

        return sorted(posts, key=lambda p: p.posted_at)