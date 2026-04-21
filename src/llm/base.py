"""LangChain-based LLM module."""

from typing import Any, Dict, List, Optional
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatResult
from langchain_core.callbacks import CallbackManagerForLLMRun

from src.common.core.config import get_settings

settings = get_settings()


def get_langchain_messages(
    system_prompt: str,
    user_prompt: str,
    history: Optional[List[Dict[str, str]]] = None
) -> List[BaseMessage]:
    """
    Convert prompts to LangChain message format.

    Args:
        system_prompt: System prompt
        user_prompt: User prompt
        history: Optional conversation history [{"role": "user", "content": "..."}]

    Returns:
        List of LangChain messages
    """
    messages = [SystemMessage(content=system_prompt)]
    if history:
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(SystemMessage(content=content))
    messages.append(HumanMessage(content=user_prompt))
    return messages


def parse_history(history: Optional[List[Dict[str, str]]]) -> List[BaseMessage]:
    """Parse history dict to LangChain messages."""
    if not history:
        return []
    return get_langchain_messages("", "", history)
