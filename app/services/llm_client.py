"""
Unified LLM client — wraps Anthropic API and Ollama interchangeably.

Set OLLAMA_BASE_URL (e.g. http://localhost:11434) to route all agent calls
through a local Ollama instance instead of the Anthropic API.
Set OLLAMA_MODEL to choose the model (default: llama3.2).
"""
import os
from dataclasses import dataclass


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
    """Call either Anthropic or Ollama depending on env config."""
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "").rstrip("/")
    if ollama_url:
        return await _call_ollama(system, user, max_tokens, temperature, ollama_url)
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
        text=choice.message.content or "",
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )
