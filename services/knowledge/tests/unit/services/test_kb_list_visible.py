"""知识库 v1 统一可见列表行为测试 — list_visible_kbs（门禁核心）。

对齐 API.md §6.1 / FRONTEND §5.3 与 ROADMAP M2 退出门禁「Knowledge Base v1
列表以一个分页端点提供当前可见集合、三类范围筛选和名称搜索，并有普通用户权限、
分页去重和搜索 Provider 测试」。

使用真实 db_session：flush 预置 User/KB 行（不 commit，session 关闭回滚）。
为避免开发库既有知识库干扰精确计数，所有预置 KB 名称携带本测试唯一的
name_token，并以 q=<name_token> 限定查询范围；scope 语义由 service 构建的
WHERE 条件在真实库上验证（同一 token 下既有行无同名匹配）。
"""

import uuid as uuid_lib

import pytest
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.services.knowledge_base_service import list_visible_kbs


def _name_token() -> str:
    return f"v1list-{uuid_lib.uuid4().hex[:12]}"


def _platform_uuid() -> str:
    return str(uuid_lib.uuid4())


async def _add_user(db, token: str, *, role: str = "user") -> User:
    user = User(
        platform_user_id=str(uuid_lib.uuid4()),
        username=f"u-{token}-{uuid_lib.uuid4().hex[:8]}",
        password_hash="x",
        role=role,
        status="active",
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def _add_kb(
    db,
    owner_id: int,
    token: str,
    label: str,
    *,
    visibility: str = "private",
    status: str = "active",
) -> KnowledgeBase:
    kb = KnowledgeBase(
        uuid=str(uuid_lib.uuid4()),
        name=f"{token}-{label}",
        user_id=owner_id,
        visibility=visibility,
        status=status,
    )
    db.add(kb)
    await db.flush()
    await db.refresh(kb)
    return kb


def _uuids(items) -> set[str]:
    return {item.uuid for item in items}


class TestScopeMine:
    @pytest.mark.asyncio
    async def test_mine_returns_own_kbs_any_status(self, db_session):
        token = _name_token()
        me = await _add_user(db_session, token)
        mine_private = await _add_kb(db_session, me.id, token, "私有库", visibility="private")
        mine_public = await _add_kb(db_session, me.id, token, "公开库", visibility="public")
        deleting = await _add_kb(
            db_session, me.id, token, "删除中", visibility="private", status="deleting"
        )

        data = await list_visible_kbs(
            db_session, me.id, "user", scope="mine", q=token, page=1, page_size=20
        )

        assert data.total == 3
        assert _uuids(data.items) == {mine_private.uuid, mine_public.uuid, deleting.uuid}


class TestScopePublic:
    @pytest.mark.asyncio
    async def test_public_returns_only_active_public(self, db_session):
        token = _name_token()
        me = await _add_user(db_session, token)
        other = await _add_user(db_session, token)
        mine_private = await _add_kb(db_session, me.id, token, "私有库", visibility="private")
        other_public = await _add_kb(db_session, other.id, token, "他人公开", visibility="public")
        inactive_public = await _add_kb(
            db_session, other.id, token, "删除中的公开", visibility="public", status="deleting"
        )

        data = await list_visible_kbs(
            db_session, me.id, "user", scope="public", q=token, page=1, page_size=20
        )

        # 仅 status=active 且 visibility=public（跨用户，含自己的公开库）
        assert data.total == 1
        assert _uuids(data.items) == {other_public.uuid}
        assert mine_private.uuid not in _uuids(data.items)
        assert inactive_public.uuid not in _uuids(data.items)


class TestScopeAll:
    @pytest.mark.asyncio
    async def test_all_is_union_and_dedup(self, db_session):
        token = _name_token()
        me = await _add_user(db_session, token)
        other = await _add_user(db_session, token)
        mine_private = await _add_kb(db_session, me.id, token, "私有库", visibility="private")
        mine_public = await _add_kb(db_session, me.id, token, "自己公开", visibility="public")
        other_public = await _add_kb(db_session, other.id, token, "他人公开", visibility="public")

        data = await list_visible_kbs(
            db_session, me.id, "user", scope="all", q=token, page=1, page_size=20
        )

        # mine ∪ public；同一 KB 只出现一次
        assert data.total == 3
        assert _uuids(data.items) == {mine_private.uuid, mine_public.uuid, other_public.uuid}

    @pytest.mark.asyncio
    async def test_all_excludes_other_private(self, db_session):
        token = _name_token()
        me = await _add_user(db_session, token)
        other = await _add_user(db_session, token)
        mine = await _add_kb(db_session, me.id, token, "我的库", visibility="private")
        other_private = await _add_kb(db_session, other.id, token, "他人私有", visibility="private")

        data = await list_visible_kbs(
            db_session, me.id, "user", scope="all", q=token, page=1, page_size=20
        )

        assert data.total == 1
        assert _uuids(data.items) == {mine.uuid}
        assert other_private.uuid not in _uuids(data.items)

    @pytest.mark.asyncio
    async def test_all_admin_sees_everything(self, db_session):
        token = _name_token()
        me = await _add_user(db_session, token)
        other = await _add_user(db_session, token)
        mine = await _add_kb(db_session, me.id, token, "我的库", visibility="private")
        other_private = await _add_kb(db_session, other.id, token, "他人私有", visibility="private")

        data = await list_visible_kbs(
            db_session, me.id, "admin", scope="all", q=token, page=1, page_size=20
        )

        # admin 治理可见：全部知识库
        assert data.total == 2
        assert _uuids(data.items) == {mine.uuid, other_private.uuid}


class TestSearch:
    @pytest.mark.asyncio
    async def test_q_filters_by_name_substring(self, db_session):
        token = _name_token()
        me = await _add_user(db_session, token)
        matched = await _add_kb(db_session, me.id, token, "合规制度汇编", visibility="private")
        await _add_kb(db_session, me.id, token, "市场分析报告", visibility="private")

        data = await list_visible_kbs(
            db_session, me.id, "user", scope="mine", q="合规制度", page=1, page_size=20
        )

        assert data.total == 1
        assert _uuids(data.items) == {matched.uuid}

    @pytest.mark.asyncio
    async def test_q_no_match_returns_empty(self, db_session):
        token = _name_token()
        me = await _add_user(db_session, token)
        await _add_kb(db_session, me.id, token, "知识库A", visibility="private")

        data = await list_visible_kbs(
            db_session, me.id, "user", scope="mine", q="不存在的关键词", page=1, page_size=20
        )

        assert data.total == 0
        assert data.items == []


class TestPaginationAndDedup:
    @pytest.mark.asyncio
    async def test_pagination_counts_only_matching_page(self, db_session):
        token = _name_token()
        me = await _add_user(db_session, token)
        kbs = [
            await _add_kb(db_session, me.id, token, f"库{i}", visibility="private")
            for i in range(3)
        ]

        page1 = await list_visible_kbs(
            db_session, me.id, "user", scope="mine", q=token, page=1, page_size=2
        )
        page2 = await list_visible_kbs(
            db_session, me.id, "user", scope="mine", q=token, page=2, page_size=2
        )

        assert page1.total == 3
        assert len(page1.items) == 2
        assert page2.total == 3
        assert len(page2.items) == 1
        # 两页并集覆盖全部 3 个知识库，无重复
        all_uuids = _uuids(page1.items) | _uuids(page2.items)
        assert all_uuids == {kb.uuid for kb in kbs}
