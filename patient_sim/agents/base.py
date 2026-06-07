"""Base LLM agent — Groq or NVIDIA NIM (OpenAI-compatible) for patient simulation."""
from __future__ import annotations
import json, logging, os
from pathlib import Path
import requests

logger = logging.getLogger(__name__)

PROVIDERS = {
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "env_keys": ("GROQ_API_KEY", "groq_api_key"),
        "secret_keys": ("GROQ_API_KEY", "groq_api_key"),
        "env_prefix": "GROQ_API_KEY=",
    },
    "nvidia": {
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "model": os.environ.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct"),
        "env_keys": ("NVIDIA_API_KEY", "NGC_API_KEY", "nvidia_api_key"),
        "secret_keys": ("NVIDIA_API_KEY", "NGC_API_KEY", "nvidia_api_key"),
        "env_prefix": "NVIDIA_API_KEY=",
    },
}


def _from_streamlit(keys: tuple[str, ...]) -> str:
    try:
        import streamlit as st
        for name in keys:
            try:
                val = st.secrets[name]
                if val:
                    return str(val).strip()
            except Exception:
                continue
    except Exception:
        pass
    return ""


def _from_env_file(prefix: str) -> str:
    try:
        root = Path(__file__).resolve().parents[2]
        env_file = root / ".env"
        if not env_file.exists():
            return ""
        for line in env_file.read_text().splitlines():
            if line.startswith(prefix):
                k = line.split("=", 1)[1].strip().strip("'\"")
                if k and not k.startswith("xxx"):
                    return k
    except Exception:
        pass
    return ""


def _pick_provider_for_key(key: str, preferred: str) -> str:
    """nvapi-* keys must use NVIDIA endpoint even if stored under GROQ_API_KEY."""
    if key.startswith("nvapi-"):
        return "nvidia"
    if key.startswith("gsk_"):
        return "groq"
    return preferred if preferred in PROVIDERS else "nvidia"


def _resolve_provider() -> tuple[str, str, str, str]:
    """Return (provider_name, api_url, model, api_key). Prefer explicit LLM_PROVIDER."""
    preferred = (
        os.environ.get("LLM_PROVIDER")
        or _from_streamlit(("LLM_PROVIDER",))
        or ""
    ).strip().lower()

    # Collect any key from env, Streamlit secrets, or .env (any known name)
    key = ""
    for env_name in ("NVIDIA_API_KEY", "NGC_API_KEY", "GROQ_API_KEY", "groq_api_key", "nvidia_api_key"):
        key = os.environ.get(env_name) or ""
        if key:
            break
    if not key:
        key = _from_streamlit(
            ("NVIDIA_API_KEY", "NGC_API_KEY", "GROQ_API_KEY", "groq_api_key", "nvidia_api_key")
        )
    if not key:
        for prefix in ("NVIDIA_API_KEY=", "NGC_API_KEY=", "GROQ_API_KEY="):
            key = _from_env_file(prefix)
            if key:
                break

    if key:
        name = _pick_provider_for_key(key.strip(), preferred)
        cfg = PROVIDERS[name]
        return name, cfg["url"], cfg["model"], key.strip()

    logger.error("No LLM API key found — set GROQ_API_KEY or NVIDIA_API_KEY in secrets/.env")
    return "groq", PROVIDERS["groq"]["url"], PROVIDERS["groq"]["model"], ""


def groq_call(system: str, user: str, json_mode: bool = True,
              max_tokens: int = 2000, temperature: float = 0.1):
    provider, api_url, model, key = _resolve_provider()

    # Groq requires "JSON" in the prompt to use json_object mode
    sys_prompt = system
    user_prompt = user
    if json_mode and "json" not in system.lower() and "json" not in user.lower():
        user_prompt = user + "\n\nRespond with valid JSON only."

    body = {
        "model": model,
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
                api_url,
                headers={"Authorization": f"Bearer {key}"},
                json=body,
                timeout=130,
            )
            # Rate limit — wait and retry
            if resp.status_code == 429:
                wait = 25 * (attempt + 1)
                logger.warning("Groq 429 rate-limit, retrying in %ds…", wait)
                _time.sleep(wait)
                continue
            # Auth failure — no point retrying
            if resp.status_code == 401:
                hint = "NVIDIA_API_KEY" if provider == "nvidia" else "GROQ_API_KEY"
                msg = (
                    f"401 Unauthorized — check {hint} in Streamlit secrets "
                    f"(NVIDIA: org.ngc.nvidia.com/setup/api-keys)"
                )
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
            last_error = f"timeout after 130s (attempt {attempt+1})"
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
