"""切片 A：来源策略（source_strategy / knowledge_base_ids）契约与持久化验收。

对齐 API.md §8（knowledge/hybrid 至少一个可读 KB、web 不接受 KB）与
DATABASE.md §5.1/5.2（research_tasks.source_strategy + research_task_knowledge_bases）。

SDD 门禁：RED —— 目标行为（来源策略字段、校验与持久化）当前缺失。
"""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.schemas.research import ResearchCreateRequest
from app.services.research_service import create_task

# 稳定 UUID（模拟 Knowledge 签发的 KB UUID）
KB_A = "11111111-1111-4111-8111-111111111111"
KB_B = "22222222-2222-4222-8222-222222222222"


def _req(**overrides) -> ResearchCreateRequest:
    base = {
        "topic": "量子计算对密码学的影响",
        "requirements": {"task_type": "analysis", "depth": "quick"},
    }
    base.update(overrides)
    return ResearchCreateRequest(**base)


class TestSourceStrategySchema:
    """请求契约：source_strategy / knowledge_base_ids 字段与校验。"""

    def test_默认web策略且无KB(self):
        req = _req()
        assert req.source_strategy == "web"
        assert req.knowledge_base_ids == []

    def test_knowledge策略带KB可创建(self):
        req = _req(source_strategy="knowledge", knowledge_base_ids=[KB_A, KB_B])
        assert req.source_strategy == "knowledge"
        assert req.knowledge_base_ids == [KB_A, KB_B]

    def test_web策略带KB_拒绝(self):
        with pytest.raises(ValidationError):
            _req(source_strategy="web", knowledge_base_ids=[KB_A])

    def test_knowledge策略无KB_拒绝(self):
        with pytest.raises(ValidationError):
            _req(source_strategy="knowledge", knowledge_base_ids=[])

    def test_hybrid策略无KB_拒绝(self):
        with pytest.raises(ValidationError):
            _req(source_strategy="hybrid", knowledge_base_ids=[])

    def test_knowledge策略KB非法UUID_拒绝(self):
        with pytest.raises(ValidationError):
            _req(source_strategy="knowledge", knowledge_base_ids=["not-a-uuid"])

    def test_超过50个KB_拒绝(self):
        many = [str(uuid.uuid4()) for _ in range(51)]
        with pytest.raises(ValidationError):
            _req(source_strategy="hybrid", knowledge_base_ids=many)

    def test_非法策略取值_拒绝(self):
        with pytest.raises(ValidationError):
            _req(source_strategy="fabric")


class TestSourceStrategyPersistence:
    """Service 层持久化：create_task 写入 source_strategy 与 KB 选择行。"""

    async def test_web策略_持久化source_strategy且无KB行(self, db_session):
        from app.models.research_task import ResearchTask

        req = _req()  # 默认 web
        result = await create_task(db_session, user_id="user-1", request=req)
        task = await db_session.get(ResearchTask, result.task_id)
        assert task.source_strategy == "web"

        # web 策略不写 KB 选择行
        from app.models.research_task_knowledge_base import ResearchTaskKnowledgeBase

        stmt = select(ResearchTaskKnowledgeBase).where(
            ResearchTaskKnowledgeBase.task_id == result.task_id
        )
        rows = (await db_session.execute(stmt)).scalars().all()
        assert rows == []

    async def test_knowledge策略_持久化source_strategy与KB行(self, db_session):
        from app.models.research_task import ResearchTask
        from app.models.research_task_knowledge_base import ResearchTaskKnowledgeBase

        req = _req(source_strategy="knowledge", knowledge_base_ids=[KB_B, KB_A])
        result = await create_task(db_session, user_id="user-1", request=req)
        task = await db_session.get(ResearchTask, result.task_id)
        assert task.source_strategy == "knowledge"

        stmt = (
            select(ResearchTaskKnowledgeBase)
            .where(ResearchTaskKnowledgeBase.task_id == result.task_id)
            .order_by(ResearchTaskKnowledgeBase.selection_order)
        )
        rows = (await db_session.execute(stmt)).scalars().all()
        assert [(r.knowledge_base_id, r.selection_order) for r in rows] == [
            (KB_B, 0),
            (KB_A, 1),
        ]

    async def test_hybrid策略_持久化source_strategy(self, db_session):
        from app.models.research_task import ResearchTask

        req = _req(source_strategy="hybrid", knowledge_base_ids=[KB_A])
        result = await create_task(db_session, user_id="user-1", request=req)
        task = await db_session.get(ResearchTask, result.task_id)
        assert task.source_strategy == "hybrid"
