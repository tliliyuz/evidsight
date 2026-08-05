"""新增 source_strategy / 幂等列与 research_task_knowledge_bases 表

Revision ID: a5b6c7d8e9f0
Revises: 33ad807896b2
Create Date: 2026-08-05

对齐 DATABASE.md §5.1 / §5.2：
- research_tasks 新增 source_strategy（knowledge/web/hybrid，默认 web）、
  idempotency_key / request_fingerprint（创建幂等，(user_id, idempotency_key) 唯一）；
- 新增 research_task_knowledge_bases 表（任务所选知识库，PK (task_id, knowledge_base_id)）。
"""

import sqlalchemy as sa
from alembic import op

revision: str = "a5b6c7d8e9f0"
down_revision: str | None = "33ad807896b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── research_tasks：来源策略 ──
    op.add_column(
        "research_tasks",
        sa.Column(
            "source_strategy",
            sa.Enum("knowledge", "web", "hybrid", name="source_strategy"),
            server_default=sa.text("'web'"),
            nullable=False,
            comment="来源策略：knowledge / web / hybrid（DATABASE.md §5.1）",
        ),
    )

    # ── research_tasks：创建幂等 ──
    op.add_column(
        "research_tasks",
        sa.Column(
            "idempotency_key",
            sa.String(128),
            server_default=sa.text("NULL"),
            nullable=True,
            comment="幂等键，(user_id, idempotency_key) 唯一",
        ),
    )
    op.add_column(
        "research_tasks",
        sa.Column(
            "request_fingerprint",
            sa.String(64),
            server_default=sa.text("NULL"),
            nullable=True,
            comment="请求内容指纹；同 Key 不同指纹拒绝",
        ),
    )
    op.create_unique_constraint(
        "uq_research_tasks_user_idempotency",
        "research_tasks",
        ["user_id", "idempotency_key"],
    )

    # ── research_task_knowledge_bases 表 ──
    op.create_table(
        "research_task_knowledge_bases",
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column(
            "knowledge_base_id",
            sa.String(36),
            nullable=False,
            comment="Knowledge 签发的稳定 KB UUID（无跨库 FK）",
        ),
        sa.Column(
            "selection_order",
            sa.Integer(),
            nullable=False,
            comment="用户选择顺序，任务内唯一且非负",
        ),
        sa.Column(
            "display_name_snapshot",
            sa.String(200),
            server_default=sa.text("NULL"),
            nullable=True,
            comment="创建任务时的名称快照，仅展示和审计使用",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["research_tasks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("task_id", "knowledge_base_id"),
    )
    # 治理影响分析索引（DATABASE.md §9 索引清单），不用于授权
    op.create_index(
        "ix_research_task_kb_kb_task",
        "research_task_knowledge_bases",
        ["knowledge_base_id", "task_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_task_kb_kb_task", table_name="research_task_knowledge_bases"
    )
    op.drop_table("research_task_knowledge_bases")
    op.drop_constraint(
        "uq_research_tasks_user_idempotency", "research_tasks", type_="unique"
    )
    op.drop_column("research_tasks", "request_fingerprint")
    op.drop_column("research_tasks", "idempotency_key")
    op.drop_column("research_tasks", "source_strategy")
