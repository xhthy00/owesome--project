"""LangChain-based LLM module."""

from typing import Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

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
        history: Optional conversation history [{"role": "user"|"assistant", "content": "..."}]

    Returns:
        List of LangChain messages
    """
    messages = [SystemMessage(content=system_prompt)]
    if history:
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("assistant", "ai"):
                messages.append(AIMessage(content=content))
            elif role == "system":
                messages.append(SystemMessage(content=content))
            else:
                messages.append(HumanMessage(content=content))
    messages.append(HumanMessage(content=user_prompt))
    return messages


def parse_history(history: Optional[List[Dict[str, str]]]) -> List[BaseMessage]:
    """Parse history dict to LangChain messages."""
    if not history:
        return []
    return get_langchain_messages("", "", history)
