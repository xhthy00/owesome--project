"""CRUD helpers for persistent AgentRun state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, desc, func
from sqlmodel import Session, select

from src.chat.models.agent_run import (
    RUN_CANCELLED,
    RUN_COMPLETE,
    RUN_FAILED,
    RUN_RUNNING,
    RUN_TODO,
    RUN_WAITING,
    ChatAgentMessage,
    ChatAgentRun,
)

_TRANSITIONS = {
    RUN_TODO: {RUN_RUNNING, RUN_FAILED, RUN_CANCELLED},
    RUN_RUNNING: {RUN_WAITING, RUN_COMPLETE, RUN_FAILED, RUN_CANCELLED},
    RUN_WAITING: {RUN_RUNNING, RUN_COMPLETE, RUN_FAILED, RUN_CANCELLED},
    RUN_COMPLETE: set(),
    RUN_FAILED: set(),
    RUN_CANCELLED: set(),
}


def create_agent_run(
    session: Session,
    *,
    conversation_id: int,
    user_id: int,
    workspace_oid: int,
    datasource_id: int | None,
    agent_mode: str,
    state: str = RUN_RUNNING,
) -> ChatAgentRun:
    """Create the next ordered run for a conversation."""
    last_order = session.exec(
        select(func.max(ChatAgentRun.run_order)).where(
            ChatAgentRun.conversation_id == conversation_id
        )
    ).one()
    run = ChatAgentRun(
        conversation_id=conversation_id,
        user_id=user_id,
        workspace_oid=workspace_oid,
        datasource_id=datasource_id,
        run_order=int(last_order or 0) + 1,
        agent_mode=agent_mode,
        state=state,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_agent_run(session: Session, run_id: int) -> ChatAgentRun | None:
    return session.get(ChatAgentRun, run_id)


def get_last_agent_run(
    session: Session,
    *,
    conversation_id: int,
    user_id: int,
    workspace_oid: int,
) -> ChatAgentRun | None:
    statement = (
        select(ChatAgentRun)
        .where(
            and_(
                ChatAgentRun.conversation_id == conversation_id,
                ChatAgentRun.user_id == user_id,
                ChatAgentRun.workspace_oid == workspace_oid,
            )
        )
        .order_by(desc(ChatAgentRun.run_order))
        .limit(1)
    )
    return session.exec(statement).first()


def get_waiting_agent_run(
    session: Session,
    *,
    conversation_id: int,
    user_id: int,
    workspace_oid: int,
) -> ChatAgentRun | None:
    statement = (
        select(ChatAgentRun)
        .where(
            and_(
                ChatAgentRun.conversation_id == conversation_id,
                ChatAgentRun.user_id == user_id,
                ChatAgentRun.workspace_oid == workspace_oid,
                ChatAgentRun.state == RUN_WAITING,
            )
        )
        .order_by(desc(ChatAgentRun.run_order))
        .limit(1)
    )
    return session.exec(statement).first()


def update_agent_run(
    session: Session,
    run: ChatAgentRun,
    *,
    state: str | None = None,
    record_id: int | None = None,
    last_speaker: str | None = None,
    message_round: int | None = None,
    retry_count: int | None = None,
    pending_payload: dict[str, Any] | None = None,
    clear_pending: bool = False,
) -> ChatAgentRun:
    """Update a run while enforcing its lifecycle transitions."""
    if state is not None and state != run.state:
        allowed = _TRANSITIONS.get(run.state, set())
        if state not in allowed:
            raise ValueError(f"Invalid AgentRun transition: {run.state} -> {state}")
        run.state = state
    if record_id is not None:
        run.record_id = record_id
    if last_speaker is not None:
        run.last_speaker = last_speaker
    if message_round is not None:
        run.message_round = message_round
    if retry_count is not None:
        run.retry_count = retry_count
    if clear_pending:
        run.pending_payload = None
    elif pending_payload is not None:
        run.pending_payload = pending_payload
    run.update_time = datetime.now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def append_agent_message(
    session: Session,
    *,
    run_id: int,
    round: int,
    sender: str,
    receiver: str | None = None,
    role: str = "assistant",
    content: str | None = None,
    action_report: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> ChatAgentMessage:
    message = ChatAgentMessage(
        run_id=run_id,
        round=round,
        sender=sender,
        receiver=receiver,
        role=role,
        content=content,
        action_report=action_report,
        context=context,
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def list_agent_messages(session: Session, run_id: int) -> list[ChatAgentMessage]:
    statement = (
        select(ChatAgentMessage)
        .where(ChatAgentMessage.run_id == run_id)
        .order_by(ChatAgentMessage.round, ChatAgentMessage.id)
    )
    return list(session.exec(statement).all())


__all__ = [
    "append_agent_message",
    "create_agent_run",
    "get_agent_run",
    "get_last_agent_run",
    "get_waiting_agent_run",
    "list_agent_messages",
    "update_agent_run",
]
