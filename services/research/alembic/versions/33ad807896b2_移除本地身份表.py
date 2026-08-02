"""移除 Research 本地身份表

Revision ID: 33ad807896b2
Revises: 22fc796785a1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "33ad807896b2"
down_revision: Union[str, Sequence[str], None] = "22fc796785a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("refresh_tokens")
    op.drop_table("users")


def downgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False, comment="bcrypt 哈希"),
        sa.Column("role", sa.Enum("user", "admin", name="user_role"), server_default=sa.text("'user'"), nullable=False),
        sa.Column("status", sa.Enum("active", "disabled", name="user_status"), server_default=sa.text("'active'"), nullable=False, comment="disabled 后拒绝登录与 Token 刷新"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(256), nullable=False, comment="refresh_token 的 SHA-256 哈希，不存明文"),
        sa.Column("expires_at", sa.DateTime(), nullable=False, comment="过期时间（创建后 7 天）"),
        sa.Column("revoked_at", sa.DateTime(), server_default=sa.text("NULL"), nullable=True, comment="吊销时间（NULL=有效，非NULL=已吊销）"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_token_hash", "refresh_tokens", ["token_hash"], unique=False)
    op.create_index("idx_user_active", "refresh_tokens", ["user_id", "revoked_at", "expires_at"], unique=False)
    op.create_index("idx_user_id", "refresh_tokens", ["user_id"], unique=False)
