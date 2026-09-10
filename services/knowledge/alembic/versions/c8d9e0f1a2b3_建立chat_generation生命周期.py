"""建立 chat_generations 生命周期事实表并关联消息。

Revision ID: c8d9e0f1a2b3
Revises: c6d7e8f9a0b1
Create Date: 2026-08-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_generations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("platform_user_id", sa.String(36), nullable=False),
        sa.Column("kb_uuid", sa.String(36), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", "canceled", name="chat_generation_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_summary", sa.String(500), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_chat_generations_status_updated", "chat_generations", ["status", "updated_at"])
    op.create_index("idx_chat_generations_conversation_created", "chat_generations", ["conversation_id", "created_at"])
    op.add_column("messages", sa.Column("generation_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_messages_generation_id", "messages", ["generation_id"])
    op.create_foreign_key(
        "fk_messages_generation_id_chat_generations",
        "messages",
        "chat_generations",
        ["generation_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_messages_generation_id_chat_generations", "messages", type_="foreignkey")
    op.drop_index("ix_messages_generation_id", table_name="messages")
    op.drop_column("messages", "generation_id")
    op.drop_index("idx_chat_generations_conversation_created", table_name="chat_generations")
    op.drop_index("idx_chat_generations_status_updated", table_name="chat_generations")
    op.drop_table("chat_generations")
