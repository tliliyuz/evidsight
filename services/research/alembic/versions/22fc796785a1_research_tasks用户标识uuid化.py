"""research_tasks 用户标识改为 Platform User UUID

Revision ID: 22fc796785a1
Revises: 11eb68567494
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "22fc796785a1"
down_revision: Union[str, Sequence[str], None] = "11eb68567494"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("research_tasks_ibfk_1", "research_tasks", type_="foreignkey")
    op.alter_column(
        "research_tasks",
        "user_id",
        existing_type=sa.BigInteger(),
        type_=sa.String(36),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "research_tasks",
        "user_id",
        existing_type=sa.String(36),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )
    op.create_foreign_key(
        "research_tasks_ibfk_1", "research_tasks", "users", ["user_id"], ["id"]
    )
