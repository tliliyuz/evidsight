"""RAG 数据清洗 cleaner 单元测试 — 页眉页脚/页号去噪 + 空白/空行规整 + 损坏 Unicode 修复

对齐 M2 数据清洗优化（ROADMAP.md §M2 范围内工作）：
- CLEAN_STRIP_BOILERPLATE：页码/页眉页脚去除
- CLEAN_NORMALIZE_WHITESPACE：空白规整 + 安全折行拼接
- CLEAN_REPAIR_UNICODE：U+FFFD / mojibake 修复
"""

import pytest

from app.rag.cleaner import (
    clean_parse_result,
    clean_text,
    is_page_number_only,
    join_wrapped_lines,
    normalize_whitespace,
    repair_broken_unicode,
    strip_page_boilerplate,
)
from app.rag.parser import ParsedPage, ParseResult


# ==================== 页号/页眉页脚 ====================


class TestIsPageNumberOnly:
    """纯页号行判定"""

    def test_纯数字_判定为页号(self):
        assert is_page_number_only("42")

    def test_符号包裹数字_判定为页号(self):
        assert is_page_number_only("- 12 -")
        assert is_page_number_only("· 12 ·")

    def test_中文页码_判定为页号(self):
        assert is_page_number_only("第 12 页")

    def test_正文行_不判定为页号(self):
        assert not is_page_number_only("第一页正文内容")
        assert not is_page_number_only("文档包含数字 123 的正文")
        assert not is_page_number_only("1. 列表项")

    def test_空行_不判定为页号(self):
        assert not is_page_number_only("")
        assert not is_page_number_only("   ")


class TestStripPageBoilerplate:
    """删除首尾页号行"""

    def test_删除首尾页号行(self):
        content = "3\n第一页正文\n42"
        assert strip_page_boilerplate(content) == "第一页正文"

    def test_删除中文页码行(self):
        content = "第 3 页\n第一页正文\n第 5 页"
        assert strip_page_boilerplate(content) == "第一页正文"

    def test_无页号_内容不变(self):
        content = "第一页正文内容"
        assert strip_page_boilerplate(content) == "第一页正文内容"

    def test_正文含数字_不误删(self):
        content = "第3章 结论\n内容含 2026 数据"
        assert strip_page_boilerplate(content) == content

    def test_空内容_安全(self):
        assert strip_page_boilerplate("") == ""
        # 纯空白行不是页号行：外层空行由 normalize_whitespace 在管线中去除
        assert strip_page_boilerplate("\n\n") == "\n\n"


# ==================== 空白/空行 ====================


class TestNormalizeWhitespace:
    """空白规整"""

    def test_折叠连续空白为单空格(self):
        assert normalize_whitespace("a   b\tc　d") == "a b c d"

    def test_去除行尾空格(self):
        assert normalize_whitespace("line1  \nline2") == "line1\nline2"

    def test_三个以上空行并为一个空行(self):
        assert normalize_whitespace("a\n\n\n\nb") == "a\n\nb"

    def test_去除外层空行(self):
        assert normalize_whitespace("\n\nfoo\n\n") == "foo"

    def test_crlf归一为lf(self):
        assert normalize_whitespace("a\r\nb") == "a\nb"

    def test_幂等(self):
        text = "a   b\tc　d\n\n\n\nline2  \n"
        assert normalize_whitespace(normalize_whitespace(text)) == normalize_whitespace(text)


class TestJoinWrappedLines:
    """安全折行拼接（PDF 断行修复）"""

    def test_无句末标点断行_拼接(self):
        assert join_wrapped_lines("这是一段很长\n的文本") == "这是一段很长的文本"

    def test_句末标点结尾_不拼接(self):
        assert join_wrapped_lines("第一句。\n第二句") == "第一句。\n第二句"
        assert join_wrapped_lines("Hello.\nWorld") == "Hello.\nWorld"

    def test_空行段落分隔_保持(self):
        assert join_wrapped_lines("标题段\n\n新段落") == "标题段\n\n新段落"

    def test_markdown标题行_不拼接进正文(self):
        assert join_wrapped_lines("# 标题\n正文内容") == "# 标题\n正文内容"

    def test_编号列表项_不拼接(self):
        assert join_wrapped_lines("1. 第一步\n2. 第二步") == "1. 第一步\n2. 第二步"

    def test_单行_不变(self):
        assert join_wrapped_lines("单独一行") == "单独一行"

    def test_空输入_安全(self):
        assert join_wrapped_lines("") == ""
        assert join_wrapped_lines("\n") == "\n"


# ==================== Unicode 修复 ====================


class TestRepairBrokenUnicode:
    """损坏 Unicode 修复"""

    def test_移除ufffd替换符(self):
        assert repair_broken_unicode("abc�def") == "abcdef"

    def test_mojibake拉丁重解码修复(self):
        # 'Ã©' 是 'é' 的 UTF-8 字节被当作 latin-1 解码
        assert repair_broken_unicode("cafÃ©") == "café"

    def test_全角ASCII归一为半角(self):
        assert repair_broken_unicode("ＡＢＣ１２３") == "ABC123"

    def test_正常中文不变(self):
        assert repair_broken_unicode("Hello 世界") == "Hello 世界"

    def test_已清洁文本不变(self):
        assert repair_broken_unicode("already clean") == "already clean"

    def test_幂等(self):
        text = "cafÃ©  � ＡＢＣ"
        assert repair_broken_unicode(repair_broken_unicode(text)) == repair_broken_unicode(text)


# ==================== 组合管线 ====================


class TestCleanTextComposite:
    """clean_text 整串管线 + 幂等"""

    def test_组合清洗管线(self):
        # 页号去噪由 strip_page_boilerplate 负责（见 TestCleanParseResult）；
        # 此处只验证 clean_text 的 Unicode 修复 + 空白规整 + 折行拼接组合
        text = "cafÃ©  � ＡＢＣ  分段\n尾页"
        result = clean_text(text)
        assert "�" not in result
        assert "café" in result
        assert "ABC" in result
        assert "  " not in result

    def test_幂等(self):
        text = "cafÃ©  是\n一段\n长文本。"
        assert clean_text(clean_text(text)) == clean_text(text)


class TestCleanParseResult:
    """clean_parse_result 页面级清洗（不改入参）"""

    def test_清洗页面并保留元数据(self):
        result = ParseResult(
            pages=[
                ParsedPage(page_number=1, content="3\n第一页正文\n42", success=True),
                ParsedPage(page_number=2, content="第 2 页\ncafÃ© ＡＢＣ", success=True),
                ParsedPage(page_number=3, content="", success=False, error="解析失败"),
            ],
            total_pages=3,
            failed_pages=1,
            source_type="pdf",
        )

        cleaned = clean_parse_result(result)

        # 入参不被修改
        assert result.pages[0].content == "3\n第一页正文\n42"
        # 元数据保留
        assert cleaned.total_pages == 3
        assert cleaned.failed_pages == 1
        assert cleaned.source_type == "pdf"
        # 成功页被清洗：页号删除 + mojibake 修复
        assert cleaned.pages[0].content == "第一页正文"
        assert "café" in cleaned.pages[1].content
        assert "42" not in cleaned.pages[1].content
        # 失败页保留原样
        assert cleaned.pages[2].content == ""
        assert cleaned.pages[2].success is False
        # full_text 反映清洗后内容
        assert "42" not in cleaned.full_text

    def test_空结果_安全(self):
        cleaned = clean_parse_result(ParseResult())
        assert cleaned.total_pages == 0
        assert cleaned.full_text == ""

    def test_开关关闭_跳过对应子步骤(self):
        """逐项开关：对应 config knob 关闭时跳过子步骤（支持 A/B 与逐项回滚）"""
        result = ParseResult(
            pages=[ParsedPage(page_number=1, content="cafÃ©  正文内容", success=True)],
            total_pages=1,
            failed_pages=0,
            source_type="pdf",
        )

        # 全部关闭：原样保留（行为与现状一致，安全回滚）
        untouched = clean_parse_result(
            result, strip_boilerplate=False, normalize_space=False, repair_unicode=False
        )
        assert untouched.pages[0].content == "cafÃ©  正文内容"

        # 仅关 unicode：空白仍规整，但 mojibake 保留
        no_unicode = clean_parse_result(result, repair_unicode=False)
        assert "cafÃ©" in no_unicode.pages[0].content
        assert "  " not in no_unicode.pages[0].content

        # 仅关空白：unicode 修复生效，但连续空格保留
        no_space = clean_parse_result(result, normalize_space=False)
        assert "café" in no_space.pages[0].content
        assert "  " in no_space.pages[0].content


class TestCleaningFeedsChunker:
    """清洗结果 → chunker 页码映射保持（不产生裸页号 chunk）"""

    def test_清洗后分块页码仍可解析(self):
        from app.rag.chunker import chunk_document

        result = ParseResult(
            pages=[
                ParsedPage(page_number=1, content="42\n第一页正文内容。", success=True),
                ParsedPage(page_number=2, content="第 2 页\n第二页内容。", success=True),
            ],
            total_pages=2,
            failed_pages=0,
            source_type="pdf",
        )

        cleaned = clean_parse_result(result)
        chunking = chunk_document(cleaned.full_text, cleaned.pages)

        assert chunking.total_chunks > 0
        # 所有 chunk 的页码元数据可解析（不为 None）
        assert all(c.page_number is not None for c in chunking.chunks)
        # 无裸页号 chunk
        assert all(not is_page_number_only(c.content.strip()) for c in chunking.chunks)
