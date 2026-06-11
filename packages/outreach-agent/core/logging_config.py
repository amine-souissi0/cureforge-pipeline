"""Structured JSON logging for services (webhook, workers)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_LOG_RECORD_BUILTINS = frozenset(logging.makeLogRecord({}).__dict__.keys()) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """One JSON object per log line; merges `logging.Logger.info(..., extra={...})` fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_BUILTINS or key.startswith("_"):
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


def configure_json_logging(level: int = logging.INFO) -> None:
    """Attach JSON formatter to the root logger (idempotent if already configured)."""
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)
