"""Unified LLM client factory — supports OpenAI, OpenRouter, Ollama, GitHub Models."""
import os
from typing import Any, Dict, List, Optional, Tuple

# Provider → (default base_url, env-var for api_key, default model)
_PROVIDER_DEFAULTS: Dict[str, Tuple[Optional[str], str, str]] = {
    "openai":        (None,                                    "OPENAI_API_KEY",     "gpt-4o-mini"),
    "openrouter":    ("https://openrouter.ai/api/v1",          "OPENROUTER_API_KEY", "openai/gpt-4o-mini"),
    "ollama":        ("http://localhost:11434/v1",              "",                   "llama3"),
    "github_models": ("https://models.inference.ai.azure.com", "GITHUB_TOKEN",       "gpt-4o-mini"),
}


def get_client(cfg: Dict[str, Any]):
    """Return (OpenAI-compatible client, model_name) from a provider config dict."""
    from openai import OpenAI  # deferred so the app works without openai installed at import time

    provider = cfg.get("provider", "openrouter")
    if provider not in _PROVIDER_DEFAULTS:
        raise ValueError(f"Unknown LLM provider '{provider}'. Choose from: {list(_PROVIDER_DEFAULTS)}")

    default_url, key_env, default_model = _PROVIDER_DEFAULTS[provider]

    api_key = cfg.get("api_key") or os.environ.get(key_env, "")
    model   = cfg.get("model")   or os.environ.get("OPENAI_MODEL", default_model)
    base_url = cfg.get("base_url") or default_url

    if provider == "ollama":
        api_key = api_key or "ollama"  # Ollama doesn't need a real key

    kwargs: Dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    return OpenAI(**kwargs), model


def llm_chat(messages: List[Dict[str, str]], cfg: Dict[str, Any], **kwargs) -> str:
    """Run a chat completion and return the assistant text."""
    try:
        client, model = get_client(cfg)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2000),
        )
        return (response.choices[0].message.content or "").strip()
    except Exception:
        return ""
