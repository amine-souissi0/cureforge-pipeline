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
    # 1. Environment variable (local .env / Docker)
    key = os.environ.get("GROQ_API_KEY") or os.environ.get("groq_api_key")
    if key:
        return key
    # 2. Streamlit Cloud secrets (st.secrets is NOT os.environ)
    try:
        import streamlit as st
        key = st.secrets.get("GROQ_API_KEY") or st.secrets.get("groq_api_key")
        if key:
            return key
    except Exception:
        pass
    logger.error("GROQ_API_KEY not found in env or st.secrets")
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
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
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
