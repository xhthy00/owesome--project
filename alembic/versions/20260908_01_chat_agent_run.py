"""create resumable chat agent run tables

Revision ID: 20260908_01
Revises: 20260907_01
Create Date: 2026-09-08
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260908_01"
down_revision = "20260907_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    json_type = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")

    if "chat_agent_run" not in tables:
        op.create_table(
            "chat_agent_run",
            sa.Column(
                "id",
                sa.BigInteger(),
                sa.Identity(always=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column("conversation_id", sa.BigInteger(), nullable=False),
            sa.Column("record_id", sa.BigInteger(), nullable=True),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("workspace_oid", sa.BigInteger(), nullable=False),
            sa.Column("datasource_id", sa.BigInteger(), nullable=True),
            sa.Column("run_order", sa.Integer(), nullable=False),
            sa.Column("agent_mode", sa.Text(), nullable=False),
            sa.Column("state", sa.Text(), nullable=False),
            sa.Column("last_speaker", sa.Text(), nullable=True),
            sa.Column("message_round", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("pending_payload", json_type, nullable=True),
            sa.Column("create_time", sa.DateTime(), nullable=True),
            sa.Column("update_time", sa.DateTime(), nullable=True),
            sa.UniqueConstraint(
                "conversation_id", "run_order", name="uq_chat_agent_run_order"
            ),
        )
        op.create_index("ix_chat_agent_run_conversation_id", "chat_agent_run", ["conversation_id"])
        op.create_index("ix_chat_agent_run_record_id", "chat_agent_run", ["record_id"])
        op.create_index("ix_chat_agent_run_user_id", "chat_agent_run", ["user_id"])
        op.create_index("ix_chat_agent_run_workspace_oid", "chat_agent_run", ["workspace_oid"])
        op.create_index("ix_chat_agent_run_state", "chat_agent_run", ["state"])

    if "chat_agent_message" not in tables:
        op.create_table(
            "chat_agent_message",
            sa.Column(
                "id",
                sa.BigInteger(),
                sa.Identity(always=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column("run_id", sa.BigInteger(), nullable=False),
            sa.Column("round", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sender", sa.Text(), nullable=False),
            sa.Column("receiver", sa.Text(), nullable=True),
            sa.Column("role", sa.Text(), nullable=False),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("action_report", json_type, nullable=True),
            sa.Column("context", json_type, nullable=True),
            sa.Column("create_time", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_chat_agent_message_run_id", "chat_agent_message", ["run_id"])
        op.create_index(
            "ix_chat_agent_message_run_round",
            "chat_agent_message",
            ["run_id", "round"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "chat_agent_message" in tables:
        op.drop_index("ix_chat_agent_message_run_round", table_name="chat_agent_message")
        op.drop_index("ix_chat_agent_message_run_id", table_name="chat_agent_message")
        op.drop_table("chat_agent_message")
    if "chat_agent_run" in tables:
        op.drop_index("ix_chat_agent_run_state", table_name="chat_agent_run")
        op.drop_index("ix_chat_agent_run_workspace_oid", table_name="chat_agent_run")
        op.drop_index("ix_chat_agent_run_user_id", table_name="chat_agent_run")
        op.drop_index("ix_chat_agent_run_record_id", table_name="chat_agent_run")
        op.drop_index("ix_chat_agent_run_conversation_id", table_name="chat_agent_run")
        op.drop_table("chat_agent_run")
