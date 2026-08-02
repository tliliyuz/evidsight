"""建立身份安全审计事件

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "identity_audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_uuid", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column(
            "outcome",
            sa.Enum("success", "denied", "error", name="identity_audit_outcome"),
            nullable=False,
        ),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_uuid", name="uq_identity_audit_event_uuid"),
    )
    op.create_index(
        "idx_identity_audit_user_created",
        "identity_audit_events",
        ["user_id", "created_at"],
    )
    op.create_index(
        "idx_identity_audit_request_id",
        "identity_audit_events",
        ["request_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_identity_audit_request_id", table_name="identity_audit_events"
    )
    op.drop_index(
        "idx_identity_audit_user_created", table_name="identity_audit_events"
    )
    op.drop_table("identity_audit_events")
