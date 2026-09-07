"""create chat_conversation_log table

Revision ID: 20260907_01
Revises: 20260820_01
Create Date: 2026-09-07
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260907_01"
down_revision = "20260820_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "chat_conversation_log" in inspector.get_table_names():
        return
    op.create_table(
        "chat_conversation_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True, nullable=False),
        sa.Column("operate", sa.Text(), nullable=False),
        sa.Column("pid", sa.BigInteger(), nullable=True),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "messages",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("reasoning_content", sa.Text(), nullable=True),
        sa.Column(
            "token_usage",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("start_time", sa.DateTime(), nullable=True),
        sa.Column("finish_time", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ai_model_name", sa.Text(), nullable=True),
    )
    op.create_index("ix_chat_conversation_log_operate", "chat_conversation_log", ["operate"])
    op.create_index("ix_chat_conversation_log_pid", "chat_conversation_log", ["pid"])
    op.create_index(
        "ix_chat_conversation_log_conversation_id", "chat_conversation_log", ["conversation_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_chat_conversation_log_conversation_id", table_name="chat_conversation_log")
    op.drop_index("ix_chat_conversation_log_pid", table_name="chat_conversation_log")
    op.drop_index("ix_chat_conversation_log_operate", table_name="chat_conversation_log")
    op.drop_table("chat_conversation_log")
