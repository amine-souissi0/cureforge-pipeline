"""OpenAI chat completion wrapper used by agents."""

from __future__ import annotations

import logging
from typing import Any, Optional

from openai import OpenAI

from config.settings import Settings, settings

logger = logging.getLogger(__name__)

_default_client: Optional[OpenAI] = None


def get_openai_client(overrides: Optional[Settings] = None) -> OpenAI:
    """Singleton OpenAI client for the process."""
    global _default_client
    cfg = overrides or settings
    if _default_client is None:
        _default_client = OpenAI(api_key=cfg.openai_api_key)
    return _default_client


def reset_openai_client_for_tests() -> None:
    """Clear cached client (tests only)."""
    global _default_client
    _default_client = None


def chat_completion_text(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float = 0.4,
    max_tokens: int = 1200,
    response_format: Optional[dict[str, str]] = None,
    client: Optional[OpenAI] = None,
) -> str:
    """
    Run a single chat completion and return assistant message text (stripped).
    """
    oai = client or get_openai_client()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    response = oai.chat.completions.create(**kwargs)
    text = (response.choices[0].message.content or "").strip()
    logger.debug("chat_completion_text: %d chars", len(text))
    return text
