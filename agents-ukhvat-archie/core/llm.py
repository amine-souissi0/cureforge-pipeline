"""
Thin wrapper around the Groq client.
All agents import this instead of instantiating Groq directly.
"""

import json
from loguru import logger
from groq import Groq
from config.settings import get_settings


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that the model sometimes adds."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Drop first line (```json or ```) and last line (```)
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return text.strip()


class LLMClient:
    """Groq-backed LLM client with JSON-safe call helper."""

    def __init__(self):
        s = get_settings()
        self.client = Groq(api_key=s.groq_api_key)
        self.model = s.groq_model

    def call(self, system: str, user: str, max_tokens: int = 1500) -> str:
        """Call the LLM and return raw text response."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return response.choices[0].message.content

    def call_json(self, system: str, user: str, max_tokens: int = 1500) -> dict | list:
        """Call the LLM and parse the response as JSON. Raises on failure."""
        raw = self.call(system, user, max_tokens)
        cleaned = _strip_fences(raw)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed. Raw response:\n{raw}")
            raise ValueError(f"LLM did not return valid JSON: {e}") from e
