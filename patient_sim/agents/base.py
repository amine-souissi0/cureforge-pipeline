"""Base Groq agent — shared LLM call for patient simulation agents."""
from __future__ import annotations
import json, logging
from pathlib import Path
import requests

logger = logging.getLogger(__name__)
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

def _get_key() -> str:
    import os
    # 1. Environment variable (local dev)
    key = os.environ.get("GROQ_API_KEY") or os.environ.get("groq_api_key")
    if key:
        return key
    # 2. Streamlit Cloud secrets
    try:
        import streamlit as st
        try:
            key = st.secrets["GROQ_API_KEY"]
        except Exception:
            try:
                key = st.secrets["groq_api_key"]
            except Exception:
                key = None
        if key:
            return str(key).strip()
    except Exception:
        pass
    # 3. .env file fallback
    try:
        root = Path(__file__).resolve().parents[2]
        env_file = root / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("GROQ_API_KEY="):
                    k = line.split("=", 1)[1].strip().strip("'\"")
                    if k:
                        return k
    except Exception:
        pass
    # 4. Empty fallback — key must be in env or Streamlit secrets
    logger.error("GROQ_API_KEY not found anywhere")
    return ""


def groq_call(system: str, user: str, json_mode: bool = True,
              max_tokens: int = 2000, temperature: float = 0.1):
    key = _get_key()

    # Groq requires "JSON" in the prompt to use json_object mode
    sys_prompt = system
    user_prompt = user
    if json_mode and "json" not in system.lower() and "json" not in user.lower():
        user_prompt = user + "\n\nRespond with valid JSON only."

    body = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "max_tokens":  max_tokens,
        "temperature": temperature,
    }
    # Note: Do NOT use response_format json_object — it causes issues on some deployments.
    # Instead we instruct the model via prompt (already done above).

    import time as _time
    last_error = "unknown"
    for attempt in range(3):
        try:
            resp = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {key}"},
                json=body,
                timeout=90,
            )
            # Rate limit — wait and retry
            if resp.status_code == 429:
                wait = 25 * (attempt + 1)
                logger.warning("Groq 429 rate-limit, retrying in %ds…", wait)
                _time.sleep(wait)
                continue
            # Auth failure — no point retrying
            if resp.status_code == 401:
                msg = f"401 Unauthorized — key='{key[:12]}...' check GROQ_API_KEY in secrets"
                logger.error(msg)
                return {"error": msg, "status": "failed"} if json_mode else f"[{msg}]"
            # Other HTTP error — log body
            if resp.status_code != 200:
                msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.error(msg)
                last_error = msg
                if attempt < 2:
                    _time.sleep(10)
                    continue
                return {"error": msg, "status": "failed"} if json_mode else f"[{msg}]"

            content = resp.json()["choices"][0]["message"]["content"].strip()
            if json_mode:
                # Strip markdown fences anywhere in the response
                if "```" in content:
                    parts = content.split("```")
                    # Find the json block
                    for part in parts:
                        stripped = part.strip()
                        if stripped.startswith("json"):
                            stripped = stripped[4:].strip()
                        if stripped.startswith("{") or stripped.startswith("["):
                            content = stripped
                            break
                content = content.strip()
                return json.loads(content)
            return content

        except requests.exceptions.Timeout:
            last_error = f"timeout after 90s (attempt {attempt+1})"
            logger.error(last_error)
            _time.sleep(10)
        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {e} — raw: {content[:100] if 'content' in dir() else '?'}"
            logger.error(last_error)
            if attempt == 2:
                return {"error": last_error, "status": "failed"} if json_mode else f"[{last_error}]"
            _time.sleep(5)
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            logger.error("Groq call failed (attempt %d): %s", attempt+1, last_error)
            if attempt == 2:
                return {"error": last_error, "status": "failed"} if json_mode else f"[{last_error}]"
            _time.sleep(5)

    return {"error": f"max retries exceeded — last: {last_error}", "status": "failed"} if json_mode else f"[{last_error}]"
