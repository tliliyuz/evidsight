"""sources 事件稳定身份（document_uuid + segment_id）单元测试。

对齐 API.md §12 / §6.2 稳定 Segment ID 契约（切片 3A）：
- build_sources 从 doc_uuid_map + chunk.segment_uuid 填充 document_uuid / segment_id
- Vector 检索从 ChromaDB metadata 读取 segment_uuid
- RRF 融合穿透 segment_uuid
- 前端据此进入文档切片抽屉并展开引用切片，不使用内部整数 id
"""

from unittest.mock import AsyncMock, patch

from app.rag.fusion import rrf_fusion
from app.rag.retriever import RetrievalOutput, RetrievalResult, VectorRetriever
from app.services.chat_service import build_sources

from tests.helpers import make_mock_chroma_results


def _make_result(
    doc_id: int,
    content: str,
    segment_uuid: str | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        doc_id=doc_id,
        chunk_index=0,
        content=content,
        score=0.9,
        segment_uuid=segment_uuid,
    )


class TestBuildSourcesStableIdentity:
    """build_sources 稳定身份填充"""

    def test_document_uuid与segment_id填充(self):
        """U7.85 扩展：doc_uuid_map 提供 document_uuid，chunk.segment_uuid 提供 segment_id"""
        results = [
            _make_result(1, "第一段检索内容", segment_uuid="seg-100"),
            _make_result(2, "第二段检索内容", segment_uuid=None),
        ]
        doc_map = {1: "文档A.pdf", 2: "文档B.md"}
        doc_uuid_map = {1: "doc-uuid-a", 2: "doc-uuid-b"}

        sources = build_sources(results, doc_map, doc_uuid_map)

        assert sources[0].document_uuid == "doc-uuid-a"
        assert sources[0].segment_id == "seg-100"
        # 无 segment_uuid 的 chunk：segment_id 为 None
        assert sources[1].document_uuid == "doc-uuid-b"
        assert sources[1].segment_id is None

    def test_doc_uuid_map缺省时document_uuid为None(self):
        """向后兼容：不传 doc_uuid_map 时 document_uuid 为 None，不抛错"""
        results = [_make_result(1, "内容", segment_uuid="seg-1")]
        sources = build_sources(results, {1: "文档.pdf"})
        assert sources[0].document_uuid is None
        assert sources[0].segment_id == "seg-1"


class TestVectorRetrieverSegmentUuid:
    """Vector 检索从 ChromaDB metadata 读取稳定 segment_uuid"""

    async def test_从metadata读取segment_uuid(self):
        """metadata 含 segment_uuid 时透传到 RetrievalResult"""
        chroma_results = make_mock_chroma_results(
            metadatas=[
                [
                    {"kb_id": 1, "doc_id": 1, "chunk_index": 0, "segment_uuid": "seg-v-1"},
                    {"kb_id": 1, "doc_id": 1, "chunk_index": 1, "segment_uuid": "seg-v-2"},
                ]
            ]
        )
        mock_store = AsyncMock()
        mock_store.search.return_value = chroma_results

        retriever = VectorRetriever(vector_store=mock_store)
        with patch("app.rag.retriever.embed_chunks", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value.embeddings = [[0.1, 0.2]]
            output = await retriever.search("测试问题", kb_id=1)

        assert output.results[0].segment_uuid == "seg-v-1"
        assert output.results[1].segment_uuid == "seg-v-2"


class TestFusionSegmentUuid:
    """RRF 融合穿透稳定 segment_uuid"""

    def test_融合结果保留segment_uuid(self):
        """两条路同 chunk 融合后，segment_uuid 不丢失"""
        vector = RetrievalOutput(results=[_make_result(1, "文档A", segment_uuid="seg-f-1")])
        bm25 = RetrievalOutput(results=[_make_result(1, "文档A", segment_uuid="seg-f-1")])

        fused = rrf_fusion(vector, bm25)

        assert fused.results[0].segment_uuid == "seg-f-1"
