"""add resolved conversation turn context

Revision ID: 20260908_02
Revises: 20260908_01
Create Date: 2026-09-08
"""

import sqlalchemy as sa

from alembic import op

revision = "20260908_02"
down_revision = "20260908_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "chat_conversation_record" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("chat_conversation_record")}
    if "resolved_question" not in existing:
        op.add_column("chat_conversation_record", sa.Column("resolved_question", sa.Text()))
    if "turn_type" not in existing:
        op.add_column(
            "chat_conversation_record",
            sa.Column("turn_type", sa.Text(), nullable=False, server_default="standalone"),
        )
    if "parent_record_id" not in existing:
        op.add_column("chat_conversation_record", sa.Column("parent_record_id", sa.BigInteger()))
        op.create_index(
            "ix_chat_conversation_record_parent_record_id",
            "chat_conversation_record",
            ["parent_record_id"],
        )
    if "context_summary" not in existing:
        op.add_column("chat_conversation_record", sa.Column("context_summary", sa.Text()))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "chat_conversation_record" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("chat_conversation_record")}
    if "context_summary" in existing:
        op.drop_column("chat_conversation_record", "context_summary")
    if "parent_record_id" in existing:
        indexes = {index["name"] for index in inspector.get_indexes("chat_conversation_record")}
        if "ix_chat_conversation_record_parent_record_id" in indexes:
            op.drop_index(
                "ix_chat_conversation_record_parent_record_id",
                table_name="chat_conversation_record",
            )
        op.drop_column("chat_conversation_record", "parent_record_id")
    if "turn_type" in existing:
        op.drop_column("chat_conversation_record", "turn_type")
    if "resolved_question" in existing:
        op.drop_column("chat_conversation_record", "resolved_question")
