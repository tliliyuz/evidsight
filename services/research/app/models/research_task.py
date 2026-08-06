"""
研究任务表 ORM 模型 —— research_tasks 表。

表结构严格遵循 [DATABASE.md §2](docs/DATABASE.md#2-表结构)。
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._types import UTCDateTime, new_uuid
from app.models.enums import (
    SOURCE_STRATEGY_ENUM,
    TASK_STATUS_ENUM,
    TASK_PHASE_ENUM,
)


class ResearchTask(Base):
    """研究任务表 —— 一次完整的研究会话。"""

    __tablename__ = "research_tasks"

    id: Mapped[str] = mapped_column(
        sa.String(36), primary_key=True, default=new_uuid
    )
    user_id: Mapped[str] = mapped_column(sa.String(36), nullable=False)

    # ── 输入 ──
    topic: Mapped[str] = mapped_column(
        sa.String(500), nullable=False, comment="用户输入的研究主题"
    )
    requirements: Mapped[dict] = mapped_column(
        sa.JSON, nullable=False, comment="研究要求（task_type, depth, max_sources, language...）"
    )
    source_strategy: Mapped[str] = mapped_column(
        sa.Enum(*SOURCE_STRATEGY_ENUM, name="source_strategy"),
        default="web",
        server_default=sa.text("'web'"),
        nullable=False,
        comment="来源策略：knowledge / web / hybrid（DATABASE.md §5.1）",
    )

    # ── 幂等（API.md §8：创建必须使用 Idempotency-Key）──
    idempotency_key: Mapped[str | None] = mapped_column(
        sa.String(128), default=None, server_default=sa.text("NULL"),
        comment="幂等键，(user_id, idempotency_key) 唯一",
    )
    request_fingerprint: Mapped[str | None] = mapped_column(
        sa.String(64), default=None, server_default=sa.text("NULL"),
        comment="请求内容指纹；同 Key 不同指纹拒绝",
    )

    # ── Level 1: Task State ──
    status: Mapped[str] = mapped_column(
        sa.Enum(*TASK_STATUS_ENUM, name="task_status"),
        default="pending",
        server_default=sa.text("'pending'"),
        nullable=False,
    )

    # ── Level 2: Phase State ──
    current_phase: Mapped[str | None] = mapped_column(
        sa.Enum(*TASK_PHASE_ENUM, name="task_phase"),
        default=None,
        server_default=sa.text("NULL"),
    )

    # ── 取消请求（DATABASE.md §5.1：取消是请求，不由 API 直接伪造终态）──
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime,
        default=None,
        server_default=sa.text("NULL"),
        comment="用户取消请求时间；Worker 在安全检查点停止后由 Resolver 推导终态",
    )

    # ── 租约（DATABASE.md §5.1 / §8：条件更新领取与续租，generation 单调递增）──
    lease_owner: Mapped[str | None] = mapped_column(
        sa.String(36),
        default=None,
        server_default=sa.text("NULL"),
        comment="当前持有租约的 Worker 标识；终态任务无有效租约",
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime,
        default=None,
        server_default=sa.text("NULL"),
        comment="租约过期时间；领取与续租使用条件更新",
    )
    lease_generation: Mapped[int] = mapped_column(
        sa.Integer,
        default=0,
        server_default=sa.text("0"),
        nullable=False,
        comment="租约代数，领取时递增；Step 提交必须匹配当前 generation",
    )

    # ── 恢复（DATABASE.md §5.1：只保存稳定游标，不保存内部摘录）──
    recovery_count: Mapped[int] = mapped_column(
        sa.Integer,
        default=0,
        server_default=sa.text("0"),
        nullable=False,
        comment="恢复扫描次数，每次 Recovery Scanner 处理递增",
    )
    last_completed_step_id: Mapped[str | None] = mapped_column(
        sa.String(36),
        default=None,
        server_default=sa.text("NULL"),
        comment="最后完成的 Step 稳定游标，恢复时从此继续",
    )

    # ── Execution Context（断点续跑核心）──
    execution_context: Mapped[dict | None] = mapped_column(
        sa.JSON, default=None, server_default=sa.text("NULL"),
    )

    # ── 统计 ──
    total_steps: Mapped[int] = mapped_column(
        sa.Integer, default=0, server_default=sa.text("0"),
    )
    completed_steps: Mapped[int] = mapped_column(
        sa.Integer, default=0, server_default=sa.text("0"),
    )
    total_sources: Mapped[int] = mapped_column(
        sa.Integer, default=0, server_default=sa.text("0"),
    )
    total_evidence: Mapped[int] = mapped_column(
        sa.Integer, default=0, server_default=sa.text("0"),
    )

    # ── Trace 追踪数据 ──
    trace: Mapped[dict | None] = mapped_column(
        sa.JSON, default=None, server_default=sa.text("NULL"),
        comment="Pipeline 七阶段 Trace JSON（TraceRecorder.finish() 产出），对齐 DATABASE.md §2.2",
    )

    # ── 错误 ──
    error_code: Mapped[str | None] = mapped_column(
        sa.String(50), default=None, server_default=sa.text("NULL"),
    )
    error_message: Mapped[str | None] = mapped_column(
        sa.Text, default=None, server_default=sa.text("NULL"),
    )
    recoverable: Mapped[bool | None] = mapped_column(
        sa.Boolean, default=None, server_default=sa.text("NULL"),
        comment="是否可以断点续跑（NULL = 未失败）",
    )

    # ── 时间 ──
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime,
        default=None,
        server_default=sa.text("NULL"),
        comment="Worker 拾取时间",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime,
        default=None,
        server_default=sa.text("NULL"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
        comment="记录最后修改时间（ORM onupdate 维护）",
    )

    # ── 索引 ──
    # idx_user_created: 覆盖 get_task_list 的 WHERE user_id=? + ORDER BY created_at DESC，避免 filesort
    # idx_user_status_created: 覆盖带 status 筛选的 get_task_list，同样避免 filesort
    # idx_status: 保留，覆盖 startup recovery / evaluation loader 等 status-only 查询
    # idx_status_lease_expires: Worker 领取与 Recovery Scanner 按 (status, lease_expires_at) 扫描（DATABASE.md §9）
    __table_args__ = (
        sa.Index("idx_status", "status"),
        sa.Index("idx_user_created", "user_id", sa.text("created_at DESC")),
        sa.Index("idx_user_status_created", "user_id", "status", sa.text("created_at DESC")),
        sa.Index("idx_status_lease_expires", "status", "lease_expires_at"),
        # 创建幂等（DATABASE.md §5.1）：(user_id, idempotency_key) 唯一；
        # idempotency_key 可空，MySQL/SQLite 对 NULL 均允许多行，不阻塞旧任务。
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_research_tasks_user_idempotency"),
    )

    # ── 关联 ──
    steps = relationship("ResearchStep", back_populates="task", lazy="selectin",
                         order_by="ResearchStep.started_at",
                         passive_deletes=True)
    sources = relationship("ResearchSource", back_populates="task", lazy="selectin",
                           passive_deletes=True)
    evidence_items = relationship("EvidenceItem", back_populates="task", lazy="selectin",
                                  passive_deletes=True)
    report_sections = relationship("ReportSection", back_populates="task", lazy="selectin",
                                   passive_deletes=True)
    agent_memory_entries = relationship("AgentMemoryEntry", back_populates="task", lazy="selectin",
                                        order_by="AgentMemoryEntry.created_at",
                                        passive_deletes=True)
    agent_events = relationship("AgentEvent", back_populates="task", lazy="selectin",
                                order_by="AgentEvent.sequence",
                                passive_deletes=True)

    def __repr__(self):
        return f"<ResearchTask(id={self.id}, topic={self.topic[:30]!r}, status={self.status})>"
