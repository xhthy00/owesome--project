"""Persistent execution state for resumable agent conversations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

RUN_TODO = "todo"
RUN_RUNNING = "running"
RUN_WAITING = "waiting"
RUN_COMPLETE = "complete"
RUN_FAILED = "failed"
RUN_CANCELLED = "cancelled"

TERMINAL_RUN_STATES = {RUN_COMPLETE, RUN_FAILED, RUN_CANCELLED}


class ChatAgentRun(SQLModel, table=True):
    """One resumable agent execution inside a chat conversation."""

    __tablename__ = "chat_agent_run"
    __table_args__ = (
        UniqueConstraint("conversation_id", "run_order", name="uq_chat_agent_run_order"),
    )

    id: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    conversation_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    record_id: Optional[int] = Field(
        default=None, sa_column=Column(BigInteger, nullable=True, index=True)
    )
    user_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    workspace_oid: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    datasource_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    run_order: int = Field(sa_column=Column(Integer, nullable=False))
    agent_mode: str = Field(sa_column=Column(Text, nullable=False))
    state: str = Field(default=RUN_TODO, sa_column=Column(Text, nullable=False, index=True))
    last_speaker: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    message_round: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    retry_count: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    pending_payload: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True),
    )
    create_time: Optional[datetime] = Field(
        default_factory=datetime.now,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )
    update_time: Optional[datetime] = Field(
        default_factory=datetime.now,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )


class ChatAgentMessage(SQLModel, table=True):
    """Agent-to-agent message persisted for retry/resume."""

    __tablename__ = "chat_agent_message"

    id: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    run_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    round: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    sender: str = Field(sa_column=Column(Text, nullable=False))
    receiver: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    role: str = Field(default="assistant", sa_column=Column(Text, nullable=False))
    content: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    action_report: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True),
    )
    context: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True),
    )
    create_time: Optional[datetime] = Field(
        default_factory=datetime.now,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )


__all__ = [
    "ChatAgentMessage",
    "ChatAgentRun",
    "RUN_CANCELLED",
    "RUN_COMPLETE",
    "RUN_FAILED",
    "RUN_RUNNING",
    "RUN_TODO",
    "RUN_WAITING",
    "TERMINAL_RUN_STATES",
]
