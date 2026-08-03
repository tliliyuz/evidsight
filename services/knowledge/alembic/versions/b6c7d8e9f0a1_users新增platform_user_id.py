"""users 新增 Platform User UUID

Revision ID: b6c7d8e9f0a1
Revises: a7b8c9d0e1f2
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 兼容历史漂移：列已存在（手动或半截迁移遗留）时跳过 ADD COLUMN，
    # 回填、NOT NULL、唯一约束仍按需执行；对全新库行为不变。
    inspector = sa.inspect(op.get_bind())
    if "platform_user_id" not in {
        col["name"] for col in inspector.get_columns("users")
    }:
        op.add_column("users", sa.Column("platform_user_id", sa.String(36), nullable=True))
    op.execute("UPDATE users SET platform_user_id = UUID() WHERE platform_user_id IS NULL")
    op.alter_column(
        "users", "platform_user_id", existing_type=sa.String(36), nullable=False
    )
    op.create_unique_constraint(
        "uq_users_platform_user_id", "users", ["platform_user_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_platform_user_id", "users", type_="unique")
    op.drop_column("users", "platform_user_id")
