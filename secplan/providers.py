"""Provider adapters: one streaming chat interface over many AI vendors.

Two client libraries cover almost every vendor:

* ``anthropic`` - Claude models via the official Anthropic SDK.
* ``openai``    - OpenAI itself plus every service that exposes an
  OpenAI-compatible Chat Completions endpoint (Gemini, Groq, OpenRouter,
  Mistral, DeepSeek, Together, and local runtimes such as Ollama / LM Studio).

API keys are passed per call and are never stored or logged by this module.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Iterator

Message = dict[str, str]  # {"role": "user" | "assistant", "content": str}


class ProviderError(Exception):
    """A user-facing error raised by a provider adapter."""


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    name: str
    kind: str  # "anthropic" | "openai_compatible"
    default_model: str
    env_key: str | None  # environment variable holding the key, if any
    base_url: str | None = None
    needs_key: bool = True
    docs_url: str = ""

    def to_public(self) -> dict:
        data = asdict(self)
        data["key_in_env"] = bool(self.env_key and os.environ.get(self.env_key))
        return data


# Model names change often; every default here can be overridden in the UI/CLI.
PROVIDERS: dict[str, ProviderSpec] = {
    p.id: p
    for p in [
        ProviderSpec("anthropic", "Anthropic (Claude)", "anthropic", "claude-opus-5-5",
                     "ANTHROPIC_API_KEY", docs_url="https://console.anthropic.com/"),
        ProviderSpec("openai", "OpenAI", "openai_compatible", "gpt-5",
                     "OPENAI_API_KEY", "https://api.openai.com/v1",
                     docs_url="https://platform.openai.com/api-keys"),
        ProviderSpec("gemini", "Google Gemini", "openai_compatible", "gemini-2.5-flash",
                     "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai/",
                     docs_url="https://aistudio.google.com/apikey"),
        ProviderSpec("groq", "Groq", "openai_compatible", "llama-3.3-70b-versatile",
                     "GROQ_API_KEY", "https://api.groq.com/openai/v1",
                     docs_url="https://console.groq.com/keys"),
        ProviderSpec("openrouter", "OpenRouter", "openai_compatible", "openai/gpt-5",
                     "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1",
                     docs_url="https://openrouter.ai/keys"),
        ProviderSpec("mistral", "Mistral", "openai_compatible", "mistral-large-latest",
                     "MISTRAL_API_KEY", "https://api.mistral.ai/v1",
                     docs_url="https://console.mistral.ai/api-keys"),
        ProviderSpec("deepseek", "DeepSeek", "openai_compatible", "deepseek-chat",
                     "DEEPSEEK_API_KEY", "https://api.deepseek.com/v1",
                     docs_url="https://platform.deepseek.com/api_keys"),
        ProviderSpec("together", "Together AI", "openai_compatible",
                     "meta-llama/Llama-3.3-70B-Instruct-Turbo", "TOGETHER_API_KEY",
                     "https://api.together.xyz/v1", docs_url="https://api.together.ai/settings/api-keys"),
        ProviderSpec("ollama", "Ollama (local)", "openai_compatible", "llama3.1",
                     None, "http://localhost:11434/v1", needs_key=False,
                     docs_url="https://ollama.com/"),
        ProviderSpec("lmstudio", "LM Studio (local)", "openai_compatible", "local-model",
                     None, "http://localhost:1234/v1", needs_key=False,
                     docs_url="https://lmstudio.ai/"),
        ProviderSpec("custom", "Custom OpenAI-compatible", "openai_compatible", "",
                     "SECPLAN_CUSTOM_API_KEY", None, needs_key=False),
    ]
}

# Claude models that accept the server-side refusal fallback parameter.
_FALLBACK_MODELS = ("claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5",
                    "claude-opus-5", "claude-sonnet-5-5")


def get_provider(provider_id: str) -> ProviderSpec:
    try:
        return PROVIDERS[provider_id]
    except KeyError:
        raise ProviderError(f"Unknown provider '{provider_id}'. "
                            f"Choose one of: {', '.join(PROVIDERS)}") from None


def resolve_key(spec: ProviderSpec, api_key: str | None) -> str | None:
    """A key supplied with the request wins; otherwise fall back to the env var."""
    if api_key:
        return api_key.strip()
    if spec.env_key:
        return os.environ.get(spec.env_key) or None
    return None


def stream_chat(
    provider_id: str,
    *,
    system: str,
    messages: list[Message],
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    max_tokens: int = 32000,
) -> Iterator[str]:
    """Yield response text chunks from the chosen provider."""
    spec = get_provider(provider_id)
    model = (model or spec.default_model).strip()
    if not model:
        raise ProviderError("A model name is required for this provider.")
    key = resolve_key(spec, api_key)
    if spec.needs_key and not key:
        hint = f" or set {spec.env_key}" if spec.env_key else ""
        raise ProviderError(f"{spec.name} needs an API key. Paste one in{hint}.")

    if spec.kind == "anthropic":
        yield from _stream_anthropic(model, key, system, messages, max_tokens)
    else:
        url = (base_url or spec.base_url or "").strip()
        if not url:
            raise ProviderError("A base URL is required for a custom provider.")
        yield from _stream_openai_compatible(spec, model, key, url, system, messages, max_tokens)


def _stream_anthropic(model: str, key: str | None, system: str,
                      messages: list[Message], max_tokens: int) -> Iterator[str]:
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    params = dict(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
    )
    try:
        if model.startswith(_FALLBACK_MODELS):
            # On a safety decline the API re-runs the request on a fallback model.
            ctx = client.beta.messages.stream(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params)
        else:
            ctx = client.messages.stream(**params)
        with ctx as stream:
            for text in stream.text_stream:
                yield text
            final = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise ProviderError("Anthropic rejected the API key.") from None
    except anthropic.NotFoundError:
        raise ProviderError(f"Anthropic model '{model}' was not found.") from None
    except anthropic.RateLimitError:
        raise ProviderError("Anthropic rate limit reached; try again shortly.") from None
    except anthropic.APIStatusError as e:
        raise ProviderError(f"Anthropic API error {e.status_code}: {e.message}") from None
    except anthropic.APIConnectionError:
        raise ProviderError("Could not reach the Anthropic API.") from None

    if final.stop_reason == "refusal":
        yield "\n\n> The model declined to continue this response."
    elif final.stop_reason == "max_tokens":
        yield "\n\n> Output hit the token limit; ask a follow-up to continue."


def _stream_openai_compatible(spec: ProviderSpec, model: str, key: str | None, base_url: str,
                              system: str, messages: list[Message],
                              max_tokens: int) -> Iterator[str]:
    import openai

    # Local runtimes ignore the key, but the client requires a non-empty string.
    client = openai.OpenAI(api_key=key or "not-needed", base_url=base_url)
    # OpenAI's newer models take max_completion_tokens; most compatible
    # servers still only understand max_tokens and cap it lower.
    limit = ({"max_completion_tokens": max_tokens} if spec.id == "openai"
             else {"max_tokens": min(max_tokens, 8192)})
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, *messages],
            stream=True,
            **limit,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except openai.AuthenticationError:
        raise ProviderError(f"{spec.name} rejected the API key.") from None
    except openai.NotFoundError:
        raise ProviderError(f"{spec.name}: model '{model}' was not found.") from None
    except openai.RateLimitError:
        raise ProviderError(f"{spec.name} rate limit reached; try again shortly.") from None
    except openai.APIStatusError as e:
        raise ProviderError(f"{spec.name} API error {e.status_code}: {e.message}") from None
    except openai.APIConnectionError:
        raise ProviderError(f"Could not reach {spec.name} at {base_url}.") from None
