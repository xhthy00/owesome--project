"""Chat models for conversation history storage."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

# SQLBot-aligned operate values for chat_conversation_log
OPERATE_GENERATE_SQL = "GENERATE_SQL"
OPERATE_GENERATE_CHART = "GENERATE_CHART"


class Conversation(SQLModel, table=True):
    """Chat conversation model."""
    __tablename__ = "chat_conversation"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True, autoincrement=True))
    user_id: int = Field(default=0, sa_column=Column(BigInteger, nullable=False, index=True))
    title: str = Field(default="", max_length=64, sa_column=Column(Text))
    datasource_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    datasource_name: Optional[str] = Field(default="", sa_column=Column(Text))
    db_type: Optional[str] = Field(default="", sa_column=Column(Text))
    oid: int = Field(default=1, sa_column=Column(BigInteger(), nullable=False))
    create_time: Optional[datetime] = Field(default_factory=datetime.now, sa_column=Column(DateTime(timezone=False)))
    update_time: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=False)))
    is_deleted: bool = Field(default=False, sa_column=Column(Boolean))


class ConversationRecord(SQLModel, table=True):
    """Chat conversation record model for storing chat messages."""
    __tablename__ = "chat_conversation_record"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True, autoincrement=True))
    conversation_id: int = Field(default=0, sa_column=Column(BigInteger, nullable=False, index=True))
    user_id: int = Field(default=0, sa_column=Column(BigInteger, nullable=False, index=True))
    question: str = Field(default="", sa_column=Column(Text))
    resolved_question: Optional[str] = Field(default=None, sa_column=Column(Text))
    turn_type: str = Field(default="standalone", sa_column=Column(Text, nullable=False))
    parent_record_id: Optional[int] = Field(
        default=None, sa_column=Column(BigInteger, nullable=True, index=True)
    )
    context_summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    sql: Optional[str] = Field(default=None, sa_column=Column(Text))
    sql_answer: Optional[str] = Field(default=None, sa_column=Column(Text))
    sql_error: Optional[str] = Field(default=None, sa_column=Column(Text))
    exec_result: Optional[str] = Field(default=None, sa_column=Column(Text))
    chart_type: Optional[str] = Field(default="table", sa_column=Column(Text))
    chart_config: Optional[str] = Field(default=None, sa_column=Column(Text))
    is_success: bool = Field(default=True, sa_column=Column(Boolean))
    finish_time: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=False)))
    create_time: Optional[datetime] = Field(default_factory=datetime.now, sa_column=Column(DateTime(timezone=False)))
    reasoning: Optional[str] = Field(default=None, sa_column=Column(Text))
    steps: Optional[str] = Field(default=None, sa_column=Column(Text))
    agent_mode: Optional[str] = Field(default=None, sa_column=Column(Text))
    plans: Optional[str] = Field(default=None, sa_column=Column(Text))
    sub_task_agents: Optional[str] = Field(default=None, sa_column=Column(Text))
    plan_states: Optional[str] = Field(default=None, sa_column=Column(Text))
    tool_calls: Optional[str] = Field(default=None, sa_column=Column(Text))
    summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    reports: Optional[str] = Field(default=None, sa_column=Column(Text))
    total_tokens: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    elapsed_ms: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))


class ConversationLog(SQLModel, table=True):
    """LLM messages snapshot per turn (SQLBot chat_log equivalent)."""

    __tablename__ = "chat_conversation_log"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True, autoincrement=True))
    operate: str = Field(default=OPERATE_GENERATE_SQL, sa_column=Column(Text, nullable=False, index=True))
    pid: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True, index=True),
        description="chat_conversation_record.id",
    )
    conversation_id: int = Field(default=0, sa_column=Column(BigInteger, nullable=False, index=True))
    messages: Optional[list[dict[str, Any]]] = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True),
    )
    reasoning_content: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    token_usage: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True),
    )
    start_time: Optional[datetime] = Field(
        default_factory=datetime.now, sa_column=Column(DateTime(timezone=False), nullable=True)
    )
    finish_time: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    error: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    ai_model_name: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
