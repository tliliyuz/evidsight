"""chat_helpers 纯函数测试 — project_wire_source canonical wire 投影。

对齐 API.md §12 来源持久化：持久化（Message.metadata.sources）与 v1 canonical
投影（chat_v1._canonical_stream）统一经 project_wire_source，单一事实，避免
两处字段漂移；剔除内部 doc_id 与 content。
"""

from app.services.chat_helpers import project_wire_source

_WIRE_KEYS = {
    "chunk_index",
    "document_uuid",
    "segment_id",
    "doc_name",
    "score",
    "page",
    "section_title",
    "section_path",
    "preview_text",
    "preview_range",
    "highlight_start",
    "highlight_end",
}


def test_project_wire_source_剔除doc_id与content():
    """投影只保留 canonical wire 字段，剔除内部 doc_id 与 content。"""
    chunk = {
        "chunk_index": 1,
        "doc_id": 42,
        "doc_name": "测试文档.pdf",
        "content": "分块正文",
        "score": 0.95,
        "document_uuid": "550e8400-e29b-41d4-a716-446655440100",
        "segment_id": "550e8400-e29b-41d4-a716-446655440001",
        "page": 3,
        "section_title": "引言",
        "section_path": "报告 > 引言",
        "preview_text": "预览",
        "preview_range": {"start": 0, "end": 10},
        "highlight_start": 2,
        "highlight_end": 8,
    }
    wire = project_wire_source(chunk)
    assert "doc_id" not in wire
    assert "content" not in wire
    assert set(wire) == _WIRE_KEYS
    assert wire["chunk_index"] == 1
    assert wire["document_uuid"] == "550e8400-e29b-41d4-a716-446655440100"
    assert wire["preview_range"] == {"start": 0, "end": 10}


def test_project_wire_source_缺省字段为None():
    """doc_uuid_map 缺失时 document_uuid/segment_id 等可选字段投影为 None（既有漂移）。"""
    chunk = {"chunk_index": 1, "doc_name": "测试文档.pdf", "score": 0.5}
    wire = project_wire_source(chunk)
    assert wire["document_uuid"] is None
    assert wire["segment_id"] is None
    assert wire["page"] is None
    assert set(wire) == _WIRE_KEYS
