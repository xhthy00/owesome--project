"""同一会话多轮：SQLBot 风格 messages 滑动窗口。"""

from __future__ import annotations

import logging
from typing import Any

from src.common.core.config import get_settings

logger = logging.getLogger(__name__)


def get_last_conversation_rounds(
    messages: list[dict[str, Any]] | None,
    rounds: int | None = None,
) -> list[dict[str, Any]]:
    """获取最后 N 轮对话（按 human 消息个数），移植自 SQLBot。"""
    if rounds is None:
        rounds = get_settings().generate_sql_query_history_round_count
    if not messages or rounds <= 0:
        return []

    human_indices: list[int] = []
    for index, msg in enumerate(messages):
        if msg.get("type") == "human":
            human_indices.append(index)

    if not human_indices:
        return []

    if len(human_indices) <= rounds:
        start_index = human_indices[0]
    else:
        start_index = human_indices[-rounds]

    return list(messages[start_index:])


def filter_non_system_messages(messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """去掉 sqlbot_system=True 的系统提示块。"""
    if not messages:
        return []
    return [obj for obj in messages if obj.get("sqlbot_system") is not True]


def load_windowed_history(
    conversation_id: int | None,
    rounds: int | None = None,
) -> list[dict[str, Any]]:
    """取最近一份 GENERATE_SQL log → 过滤系统提示 → 按轮数截窗。"""
    if not conversation_id:
        return []
    if rounds is None:
        rounds = get_settings().generate_sql_query_history_round_count
    if rounds <= 0:
        return []
    try:
        from src.chat.crud.chat import list_generate_sql_logs
        from src.common.core.database import get_db_session

        with get_db_session() as session:
            logs = list_generate_sql_logs(session, int(conversation_id))
        if not logs:
            return []
        last = logs[-1]
        filtered = filter_non_system_messages(last.messages or [])
        return get_last_conversation_rounds(filtered, rounds=rounds)
    except Exception as exc:  # noqa: BLE001
        logger.warning("load_windowed_history failed: %s", exc)
        return []


def to_role_dicts(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """SQLBot type 格式 → OpenAI role 格式（供 Agent / build_chat_messages）。"""
    out: list[dict[str, str]] = []
    for msg in messages:
        content = str(msg.get("content") or "")
        if not content:
            continue
        msg_type = str(msg.get("type") or "human")
        if msg_type == "ai":
            out.append({"role": "assistant", "content": content})
        elif msg_type == "system":
            out.append({"role": "system", "content": content})
        else:
            out.append({"role": "user", "content": content})
    return out


def make_log_message(msg_type: str, content: str, *, sqlbot_system: bool = False) -> dict[str, Any]:
    return {
        "type": msg_type,
        "content": content,
        "sqlbot_system": sqlbot_system,
    }


def build_turn_log_messages(
    *,
    system_blocks: list[dict[str, Any]] | None = None,
    history: list[dict[str, Any]] | None = None,
    human_content: str,
    ai_content: str,
) -> list[dict[str, Any]]:
    """组装本轮写入 chat_log 的完整 messages（系统块 + 窗口历史 + 本轮问答）。"""
    messages: list[dict[str, Any]] = []
    if system_blocks:
        messages.extend(system_blocks)
    if history:
        messages.extend(history)
    messages.append(make_log_message("human", human_content))
    messages.append(make_log_message("ai", ai_content))
    return messages


def persist_generate_sql_log(
    *,
    conversation_id: int,
    record_id: int | None,
    messages: list[dict[str, Any]],
    reasoning_content: str | None = None,
    error: bool = False,
    ai_model_name: str | None = None,
) -> None:
    """短事务写入一份 GENERATE_SQL chat_log。"""
    if not conversation_id:
        return
    try:
        from src.chat.crud.chat import end_conversation_log, start_conversation_log
        from src.common.core.database import get_db_session

        with get_db_session() as session:
            log = start_conversation_log(
                session,
                conversation_id=conversation_id,
                pid=record_id,
                messages=messages,
                ai_model_name=ai_model_name,
            )
            end_conversation_log(
                session,
                log,
                messages=messages,
                reasoning_content=reasoning_content,
                error=error,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("persist_generate_sql_log failed: %s", exc)


__all__ = [
    "build_turn_log_messages",
    "filter_non_system_messages",
    "get_last_conversation_rounds",
    "load_windowed_history",
    "make_log_message",
    "persist_generate_sql_log",
    "to_role_dicts",
]
