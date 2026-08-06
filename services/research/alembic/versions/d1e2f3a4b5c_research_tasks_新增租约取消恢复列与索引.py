"""research_tasks 新增租约/取消/恢复列与索引

Revision ID: d1e2f3a4b5c
Revises: c0d1e2f3a4b5
Create Date: 2026-08-06

对齐 DATABASE.md §5.1 / §8 与 RESEARCH_PIPELINE §13 / ADR-008：
- 新增取消请求列 `cancel_requested_at`（取消是请求，不由 API 直接伪造终态）；
- 新增租约列 `lease_owner` / `lease_expires_at` / `lease_generation`
  （Worker 领取与续租使用条件更新；generation 单调递增；Step 提交必须匹配）；
- 新增恢复列 `recovery_count` / `last_completed_step_id`（只保存稳定游标）；
- 新增索引 `idx_status_lease_expires`（Worker 领取与 Recovery Scanner 按
  (status, lease_expires_at) 扫描）。
"""

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c"
down_revision: str | None = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 取消请求（DATABASE.md §5.1 控制组）──
    op.add_column(
        "research_tasks",
        sa.Column(
            "cancel_requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NULL"),
            nullable=True,
            comment="用户取消请求时间；Worker 在安全检查点停止后由 Resolver 推导终态",
        ),
    )

    # ── 租约（DATABASE.md §5.1 租约组 / §8）──
    op.add_column(
        "research_tasks",
        sa.Column(
            "lease_owner",
            sa.String(36),
            server_default=sa.text("NULL"),
            nullable=True,
            comment="当前持有租约的 Worker 标识；终态任务无有效租约",
        ),
    )
    op.add_column(
        "research_tasks",
        sa.Column(
            "lease_expires_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NULL"),
            nullable=True,
            comment="租约过期时间；领取与续租使用条件更新",
        ),
    )
    op.add_column(
        "research_tasks",
        sa.Column(
            "lease_generation",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="租约代数，领取时递增；Step 提交必须匹配当前 generation",
        ),
    )

    # ── 恢复（DATABASE.md §5.1 恢复组：只保存稳定游标）──
    op.add_column(
        "research_tasks",
        sa.Column(
            "recovery_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="恢复扫描次数，每次 Recovery Scanner 处理递增",
        ),
    )
    op.add_column(
        "research_tasks",
        sa.Column(
            "last_completed_step_id",
            sa.String(36),
            server_default=sa.text("NULL"),
            nullable=True,
            comment="最后完成的 Step 稳定游标，恢复时从此继续",
        ),
    )

    # ── 索引（DATABASE.md §9：Worker 领取与恢复扫描）──
    op.create_index(
        "idx_status_lease_expires",
        "research_tasks",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_status_lease_expires", table_name="research_tasks")
    op.drop_column("research_tasks", "last_completed_step_id")
    op.drop_column("research_tasks", "recovery_count")
    op.drop_column("research_tasks", "lease_generation")
    op.drop_column("research_tasks", "lease_expires_at")
    op.drop_column("research_tasks", "lease_owner")
    op.drop_column("research_tasks", "cancel_requested_at")
