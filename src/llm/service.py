"""LLM service factory using LangChain."""

from typing import Optional

from src.common.core.config import get_settings
from src.llm.base import get_langchain_messages, parse_history
from src.llm.openai import OpenAILLM
from src.llm.ollama import OllamaLLM

settings = get_settings()


def get_llm_provider() -> str:
    """Detect LLM provider from base_url."""
    base_url = settings.llm_base_url or ""

    if "ollama" in base_url.lower() or not base_url:
        return "ollama"
    return "openai"


def create_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **kwargs
):
    """
    Factory function to create LLM instance using LangChain.

    Args:
        provider: "openai", "ollama", or "auto" (default)
        model: Model name
        api_key: API key
        base_url: API base URL
        **kwargs: Additional parameters

    Returns:
        LLM instance (OpenAILLM or OllamaLLM)
    """
    if provider == "auto" or not provider:
        provider = get_llm_provider()

    model = model or settings.llm_model
    api_key = api_key or settings.llm_api_key
    base_url = base_url or settings.llm_base_url

    if provider.lower() == "ollama":
        return OllamaLLM(
            model=model,
            base_url=base_url,
            **kwargs
        )
    else:
        return OpenAILLM(
            model=model,
            api_key=api_key,
            base_url=base_url,
            **kwargs
        )


# Default LLM instance
_default_llm = None


def get_default_llm():
    """Get default LLM instance (singleton)."""
    global _default_llm
    if _default_llm is None:
        _default_llm = create_llm()
    return _default_llm


def build_chat_messages(
    system_prompt: str,
    user_prompt: str,
    history: Optional[list] = None
):
    """Build message list for chat completion using LangChain format."""
    return get_langchain_messages(system_prompt, user_prompt, history)
