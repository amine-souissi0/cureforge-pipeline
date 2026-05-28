"""
Unified LLM client — wraps Anthropic API, OpenAI, Groq, Gemini, and Ollama interchangeably.

Provider selection (first match wins):
  OLLAMA_BASE_URL set  → Ollama  (OLLAMA_MODEL, default: llama3.2)
  OPENAI_API_KEY set   → OpenAI  (OPENAI_MODEL, default: gpt-4o-mini)
  GROQ_API_KEY set     → Groq    (GROQ_MODEL, default: llama-3.3-70b-versatile)
  GEMINI_API_KEY set   → Gemini  (GEMINI_MODEL, default: gemini-2.0-flash)
  Otherwise            → Anthropic (ANTHROPIC_API_KEY required)
"""
import os
from dataclasses import dataclass

_OPENAI_BASE_URL = "https://api.openai.com/v1"
_OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
_GEMINI_DEFAULT_MODEL = "gemini-2.0-flash"


def _strip_markdown(text: str) -> str:
    """Extract JSON from model output — handles fences, prose wrappers, and raw JSON."""
    import re
    text = text.strip()
    # Strip code fences first
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
        text = text.strip()
    # If already valid JSON, return as-is
    if text.startswith("{") or text.startswith("["):
        return text
    # Extract the first complete JSON object from prose output
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return match.group(0)
    return text


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int


async def call_llm(
    *,
    system: str,
    user: str,
    model: str,
    max_tokens: int,
    temperature: float = 0.0,
) -> LLMResponse:
    """Call OpenAI, Anthropic, Groq, Gemini, or Ollama depending on env config."""
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "").rstrip("/")
    if ollama_url:
        return await _call_ollama(system, user, max_tokens, temperature, ollama_url)
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        return await _call_openai(system, user, max_tokens, temperature, openai_key)
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if groq_key:
        return await _call_groq(system, user, max_tokens, temperature, groq_key)
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        return await _call_gemini(system, user, max_tokens, temperature, gemini_key)
    return await _call_anthropic(system, user, model, max_tokens, temperature)


async def _call_anthropic(
    system: str,
    user: str,
    model: str,
    max_tokens: int,
    temperature: float,
) -> LLMResponse:
    import anthropic
    from app.config import get_anthropic_api_key

    client = anthropic.AsyncAnthropic(api_key=get_anthropic_api_key())
    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    block = response.content[0]
    return LLMResponse(
        text=getattr(block, "text", ""),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )


async def _call_openai(
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
    api_key: str,
) -> LLMResponse:
    import openai

    openai_model = os.environ.get("OPENAI_MODEL", _OPENAI_DEFAULT_MODEL)
    client = openai.AsyncOpenAI(base_url=_OPENAI_BASE_URL, api_key=api_key)
    response = await client.chat.completions.create(
        model=openai_model,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    choice = response.choices[0]
    usage = response.usage
    return LLMResponse(
        text=_strip_markdown(choice.message.content or ""),
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )


async def _call_groq(
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
    api_key: str,
) -> LLMResponse:
    import openai

    groq_model = os.environ.get("GROQ_MODEL", _GROQ_DEFAULT_MODEL)
    client = openai.AsyncOpenAI(base_url=_GROQ_BASE_URL, api_key=api_key)
    response = await client.chat.completions.create(
        model=groq_model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    choice = response.choices[0]
    usage = response.usage
    return LLMResponse(
        text=_strip_markdown(choice.message.content or ""),
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )


async def _call_gemini(
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
    api_key: str,
) -> LLMResponse:
    import openai

    gemini_model = os.environ.get("GEMINI_MODEL", _GEMINI_DEFAULT_MODEL)
    client = openai.AsyncOpenAI(base_url=_GEMINI_BASE_URL, api_key=api_key)
    response = await client.chat.completions.create(
        model=gemini_model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    choice = response.choices[0]
    usage = response.usage
    return LLMResponse(
        text=_strip_markdown(choice.message.content or ""),
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )


async def _call_ollama(
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
    base_url: str,
) -> LLMResponse:
    import openai

    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    client = openai.AsyncOpenAI(base_url=f"{base_url}/v1", api_key="ollama")
    response = await client.chat.completions.create(
        model=ollama_model,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    choice = response.choices[0]
    usage = response.usage
    return LLMResponse(
        text=_strip_markdown(choice.message.content or ""),
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )
