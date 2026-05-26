"""
Unified LLM client — wraps Anthropic API, Groq, and Ollama interchangeably.

Provider selection (first match wins):
  OLLAMA_BASE_URL set  → Ollama  (OLLAMA_MODEL, default: llama3.2)
  GROQ_API_KEY set     → Groq    (GROQ_MODEL, default: llama-3.3-70b-versatile)
  Otherwise            → Anthropic (ANTHROPIC_API_KEY required)
"""
import os
from dataclasses import dataclass

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"


def _strip_markdown(text: str) -> str:
    """Strip markdown code fences that open-source models add around JSON output."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]  # drop the opening ```json line
        text = text.rsplit("```", 1)[0]  # drop the closing ```
    return text.strip()


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
    """Call Anthropic, Groq, or Ollama depending on env config."""
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "").rstrip("/")
    if ollama_url:
        return await _call_ollama(system, user, max_tokens, temperature, ollama_url)
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if groq_key:
        return await _call_groq(system, user, max_tokens, temperature, groq_key)
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
