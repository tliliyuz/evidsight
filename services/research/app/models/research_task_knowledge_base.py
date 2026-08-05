"""研究任务知识库选择表 ORM 模型 —— research_task_knowledge_bases 表。

对齐 DATABASE.md §5.2：
- 主键 (task_id, knowledge_base_id)，级联删除；
- knowledge_base_id 是 Knowledge 签发的稳定 UUID，无跨库外键；
- selection_order 为用户选择顺序，任务内唯一且非负；
- display_name_snapshot 仅展示和审计使用，不证明 KB 存在或用户有权访问。
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._types import UTCDateTime


class ResearchTaskKnowledgeBase(Base):
    """一次研究任务所选知识库的关系行（多对多中间表）。"""

    __tablename__ = "research_task_knowledge_bases"

    task_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("research_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        sa.String(36),
        primary_key=True,
        comment="Knowledge 签发的稳定 KB UUID（无跨库 FK）",
    )
    selection_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, comment="用户选择顺序，任务内唯一且非负"
    )
    display_name_snapshot: Mapped[str | None] = mapped_column(
        sa.String(200),
        default=None,
        server_default=sa.text("NULL"),
        comment="创建任务时的名称快照，仅展示和审计使用",
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ResearchTaskKnowledgeBase(task_id={self.task_id}, "
            f"knowledge_base_id={self.knowledge_base_id}, "
            f"selection_order={self.selection_order})>"
        )
