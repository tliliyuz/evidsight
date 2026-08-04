"""KB 权限纯函数矩阵测试 — 对齐 PRD §8.2 权限矩阵与 IDENTITY_AND_ACCESS §8 执行规则

矩阵语义（PRD §8.2）：
- READ 由 visibility 优先决定：public→所有登录用户，private→owner+admin；
- WRITE 由 ownership 决定，admin 提供治理覆盖：owner+admin 可删/改元数据；
- owner-only：上传文档仅 owner，admin 作为非 owner 同样不可代传（PRD §8.2 admin 列 ❌）。

权限函数操作已加载的 KnowledgeBase 对象，不触发 DB 查询。
"""
import pytest

from app.core.exceptions import PermissionDeniedException
from app.core.permissions import require_kb_owner, require_kb_readable, require_kb_writable
from app.models.knowledge_base import KnowledgeBase


def _kb(*, owner_id=1, visibility="private"):
    """构造内存中的 KnowledgeBase 对象（不写库）。"""
    kb = KnowledgeBase()
    kb.user_id = owner_id
    kb.visibility = visibility
    return kb


class TestRequireKbReadable:
    """PRD §8.2「查看知识库 / 问答检索 / 研究引用」— READ 由 visibility 优先决定。"""

    def test_owner_reads_own_private_kb(self):
        require_kb_readable(_kb(owner_id=1, visibility="private"), 1, "user")

    def test_owner_reads_own_public_kb(self):
        require_kb_readable(_kb(owner_id=1, visibility="public"), 1, "user")

    def test_other_user_cannot_read_private_kb(self):
        with pytest.raises(PermissionDeniedException):
            require_kb_readable(_kb(owner_id=1, visibility="private"), 2, "user")

    def test_other_user_reads_public_kb(self):
        require_kb_readable(_kb(owner_id=1, visibility="public"), 2, "user")

    def test_admin_reads_others_private_kb(self):
        require_kb_readable(_kb(owner_id=1, visibility="private"), 2, "admin")

    def test_admin_reads_public_kb(self):
        require_kb_readable(_kb(owner_id=1, visibility="public"), 2, "admin")


class TestRequireKbWritable:
    """PRD §8.2「编辑元数据 / 删除知识库 / 删除文档」— WRITE 由 ownership 决定，admin 治理覆盖。"""

    def test_owner_writes_own_private_kb(self):
        require_kb_writable(_kb(owner_id=1, visibility="private"), 1, "user")

    def test_owner_writes_own_public_kb(self):
        require_kb_writable(_kb(owner_id=1, visibility="public"), 1, "user")

    def test_other_user_cannot_write_private_kb(self):
        with pytest.raises(PermissionDeniedException):
            require_kb_writable(_kb(owner_id=1, visibility="private"), 2, "user")

    def test_other_user_cannot_write_public_kb(self):
        with pytest.raises(PermissionDeniedException):
            require_kb_writable(_kb(owner_id=1, visibility="public"), 2, "user")

    def test_admin_writes_others_private_kb_as_governance(self):
        require_kb_writable(_kb(owner_id=1, visibility="private"), 2, "admin")


class TestRequireKbOwner:
    """PRD §8.2「上传文档」— owner-only，admin 作为非 owner 同样不可代传。"""

    def test_owner_uploads_to_private_kb(self):
        require_kb_owner(_kb(owner_id=1, visibility="private"), 1)

    def test_owner_uploads_to_public_kb(self):
        require_kb_owner(_kb(owner_id=1, visibility="public"), 1)

    def test_other_user_cannot_upload(self):
        with pytest.raises(PermissionDeniedException):
            require_kb_owner(_kb(owner_id=1), 2)

    def test_admin_not_owner_cannot_upload(self):
        """admin 治理权限不替代资源所有权：非 owner 一律拒绝。"""
        with pytest.raises(PermissionDeniedException):
            require_kb_owner(_kb(owner_id=1), 2)
