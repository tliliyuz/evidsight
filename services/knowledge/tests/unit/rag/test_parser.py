"""文档解析器单元测试 — 覆盖 PDF/DOCX/MD/TXT 解析 + 容错阈值判定 + 表格 Markdown 转换"""

import pytest
from unittest.mock import MagicMock, PropertyMock, patch

from app.rag.parser import (
    ParsedPage,
    ParseResult,
    parse_document,
    _parse_pdf,
    _parse_pdf_with_pdfplumber,
    _parse_docx,
    _parse_text,
    _table_to_markdown,
)


# === 辅助工具 ===


def _make_fitz_page(text: str, tables: list | None = None) -> MagicMock:
    """创建 mock fitz 页面对象"""
    page = MagicMock()
    page.get_text.return_value = text
    page.find_tables.return_value = tables if tables is not None else []
    return page


def _make_fitz_doc(pages: list[MagicMock]) -> MagicMock:
    """创建 mock fitz 文档对象，支持 len() 和 [] 索引"""
    doc = MagicMock()
    doc.__len__.return_value = len(pages)
    doc.__getitem__.side_effect = lambda i: pages[i]
    return doc


def _make_pdfplumber_page(text: str) -> MagicMock:
    """创建 mock pdfplumber 页面对象"""
    page = MagicMock()
    page.extract_text.return_value = text
    return page


class TestParsedPage:
    """ParsedPage 数据类测试"""

    def test_正常页面_默认创建(self):
        page = ParsedPage(page_number=1, content="测试内容")
        assert page.page_number == 1
        assert page.content == "测试内容"
        assert page.success is True
        assert page.error is None

    def test_失败页面_记录错误信息(self):
        page = ParsedPage(page_number=3, content="", success=False, error="解析异常")
        assert page.success is False
        assert page.error == "解析异常"
        assert page.content == ""


class TestParseResult:
    """ParseResult 聚合结果测试"""

    def test_failure_rate_全部成功_返回0(self):
        result = ParseResult(
            pages=[ParsedPage(1, "a"), ParsedPage(2, "b")], total_pages=2, failed_pages=0
        )
        assert result.failure_rate == 0.0

    def test_failure_rate_全部失败_返回1(self):
        result = ParseResult(
            pages=[ParsedPage(1, "", success=False)], total_pages=1, failed_pages=1
        )
        assert result.failure_rate == 1.0

    def test_failure_rate_一半失败(self):
        result = ParseResult(
            pages=[
                ParsedPage(1, "ok"),
                ParsedPage(2, "", success=False),
            ],
            total_pages=2,
            failed_pages=1,
        )
        assert result.failure_rate == 0.5

    def test_failure_rate_空文档_视为全部失败(self):
        result = ParseResult(total_pages=0, failed_pages=0)
        assert result.failure_rate == 1.0

    def test_full_text_仅拼接成功页面(self):
        result = ParseResult(
            pages=[
                ParsedPage(1, "第一页"),
                ParsedPage(2, "", success=False),
                ParsedPage(3, "第三页"),
            ],
            total_pages=3,
            failed_pages=1,
        )
        assert result.full_text == "第一页\n\n第三页"

    def test_full_text_全部失败_返回空串(self):
        result = ParseResult(
            pages=[ParsedPage(1, "", success=False, error="err")], total_pages=1, failed_pages=1
        )
        assert result.full_text == ""

    def test_warnings_收集所有失败页面(self):
        result = ParseResult(
            pages=[
                ParsedPage(1, "ok"),
                ParsedPage(2, "", success=False, error="第2页错误"),
                ParsedPage(3, "", success=False, error="第3页错误"),
            ],
            total_pages=3,
            failed_pages=2,
        )
        warnings = result.warnings
        assert len(warnings) == 2
        assert "第2页: 第2页错误" in warnings
        assert "第3页: 第3页错误" in warnings

    def test_warnings_无失败_返回空列表(self):
        result = ParseResult(pages=[ParsedPage(1, "ok")], total_pages=1, failed_pages=0)
        assert result.warnings == []


class TestParseText:
    """纯文本解析测试（md/txt）"""

    def test_txt_正常解析(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("这是一段测试文本。\n\n包含两段内容。", encoding="utf-8")

        result = _parse_text(str(file_path))
        assert result.total_pages == 1
        assert result.failed_pages == 0
        assert result.failure_rate == 0.0
        assert "测试文本" in result.full_text

    def test_md_正常解析(self, tmp_path):
        file_path = tmp_path / "readme.md"
        file_path.write_text("# 标题\n\n正文内容，**加粗**文字。", encoding="utf-8")

        result = _parse_text(str(file_path))
        assert result.failed_pages == 0
        assert "# 标题" in result.full_text
        assert result.failure_rate == 0.0

    def test_空文件_返回失败(self, tmp_path):
        file_path = tmp_path / "empty.txt"
        file_path.write_text("", encoding="utf-8")

        result = _parse_text(str(file_path))
        assert result.failed_pages == 1
        assert result.failure_rate == 1.0
        assert "内容为空" in result.pages[0].error

    def test_gbk编码_自动回退解析(self, tmp_path):
        file_path = tmp_path / "gbk.txt"
        file_path.write_bytes("GBK编码测试内容".encode("gbk"))

        result = _parse_text(str(file_path))
        assert result.failed_pages == 0
        assert "GBK编码测试内容" in result.full_text

    def test_文件不存在_返回失败(self):
        result = _parse_text("/nonexistent/file.txt")
        assert result.failed_pages == 1
        assert result.failure_rate == 1.0


class TestParsePdf:
    """PDF 解析测试（Mock pymupdf + pdfplumber）"""

    def test_正常PDF_逐页解析全部成功(self):
        """pymupdf 主力模式：3 页均含文本，无表格"""
        pages = [
            _make_fitz_page("第一页内容"),
            _make_fitz_page("第二页内容"),
            _make_fitz_page("第三页内容"),
        ]
        mock_doc = _make_fitz_doc(pages)

        with patch("app.rag.parser.fitz.open", return_value=mock_doc):
            result = _parse_pdf("test.pdf")

        assert result.total_pages == 3
        assert result.failed_pages == 0
        assert result.failure_rate == 0.0
        assert len(result.pages) == 3
        assert result.pages[0].content == "第一页内容"
        assert result.pages[2].page_number == 3
        assert result.pages[0].element_types == ["text"]
        assert result.pages[0].tables == []

    def test_部分页面无文本_标记失败(self):
        """第 2 页无文本 → 标记 failed"""
        pages = [
            _make_fitz_page("OK"),
            _make_fitz_page(""),
            _make_fitz_page("OK"),
        ]
        mock_doc = _make_fitz_doc(pages)

        with patch("app.rag.parser.fitz.open", return_value=mock_doc):
            result = _parse_pdf("test.pdf")

        assert result.total_pages == 3
        assert result.failed_pages == 1
        assert not result.pages[1].success
        assert "无文本" in result.pages[1].error

    def test_单页解析异常_跳过继续(self):
        """第 2 页 get_text 抛异常 → 跳过，其他页正常"""
        page_ok = _make_fitz_page("OK")
        page_bad = MagicMock()
        page_bad.get_text.side_effect = RuntimeError("PDF 解析错误")
        page_bad.find_tables.return_value = []
        pages = [page_ok, page_bad]
        mock_doc = _make_fitz_doc(pages)

        with patch("app.rag.parser.fitz.open", return_value=mock_doc):
            result = _parse_pdf("test.pdf")

        assert result.failed_pages == 1
        assert result.pages[0].success is True
        assert result.pages[1].success is False
        assert "PDF 解析错误" in result.pages[1].error

    def test_全部页面失败(self):
        """所有页面均无文本或异常 → failure_rate=1.0"""
        pages = [
            _make_fitz_page(""),
            _make_fitz_page("   "),
        ]
        mock_doc = _make_fitz_doc(pages)

        with patch("app.rag.parser.fitz.open", return_value=mock_doc):
            result = _parse_pdf("test.pdf")

        assert result.failed_pages == 2
        assert result.failure_rate == 1.0

    def test_pymupdf打开失败_降级到pdfplumber(self):
        """fitz.open 异常 → pdfplumber 全量降级"""
        with patch("app.rag.parser.fitz.open", side_effect=ValueError("PDF 文件已损坏")):
            plumber_page = _make_pdfplumber_page("降级提取的文本")
            mock_plumber = MagicMock()
            mock_plumber.pages = [plumber_page, plumber_page]

            with patch("app.rag.parser.pdfplumber.open", return_value=mock_plumber):
                result = _parse_pdf("corrupted.pdf")

        assert result.total_pages == 2
        assert result.failed_pages == 0
        assert result.pages[0].content == "降级提取的文本"

    def test_两引擎均失败(self):
        """fitz.open + pdfplumber.open 均异常 → 全部失败"""
        with patch("app.rag.parser.fitz.open", side_effect=ValueError("fitz 错误")):
            with patch("app.rag.parser.pdfplumber.open", side_effect=RuntimeError("plumber 错误")):
                result = _parse_pdf("bad.pdf")

        assert result.failed_pages == 1
        assert result.failure_rate == 1.0
        assert "fitz 错误" in result.pages[0].error
        assert "plumber 错误" in result.pages[0].error

    def test_空文档_0页(self):
        """0 页 PDF → ParseResult 正常返回，failure_rate=1.0"""
        mock_doc = _make_fitz_doc([])

        with patch("app.rag.parser.fitz.open", return_value=mock_doc):
            result = _parse_pdf("empty.pdf")

        assert result.total_pages == 0
        assert result.failure_rate == 1.0

    def test_含表格页面_表格嵌入content为Markdown(self):
        """pymupdf 检测到表格 → pdfplumber 提取 → Markdown 嵌入 content"""
        page_with_table = _make_fitz_page("页面文本段落", tables=[MagicMock()])

        mock_doc = _make_fitz_doc([page_with_table])

        # pdfplumber 返回表格数据
        plumber_page = MagicMock()
        plumber_page.extract_tables.return_value = [
            [["姓名", "年龄"], ["张三", "30"], ["李四", "25"]]
        ]

        mock_plumber = MagicMock()
        mock_plumber.pages = [plumber_page]

        with patch("app.rag.parser.fitz.open", return_value=mock_doc):
            with patch("app.rag.parser.pdfplumber.open", return_value=mock_plumber):
                result = _parse_pdf("table.pdf")

        assert result.total_pages == 1
        assert result.failed_pages == 0
        assert "页面文本段落" in result.pages[0].content
        assert "| 姓名 | 年龄 |" in result.pages[0].content
        assert "| 张三 | 30 |" in result.pages[0].content
        assert result.pages[0].element_types == ["text", "table"]
        assert len(result.pages[0].tables) == 1

    def test_无表格页面_pdfplumber不被调用(self):
        """find_tables 返回空 → 不打开 pdfplumber（零开销）"""
        page = _make_fitz_page("纯文本页面，无表格", tables=[])

        mock_doc = _make_fitz_doc([page])

        with patch("app.rag.parser.fitz.open", return_value=mock_doc):
            result = _parse_pdf("notext.pdf")

        assert result.total_pages == 1
        assert result.failed_pages == 0
        assert result.pages[0].content == "纯文本页面，无表格"
        assert result.pages[0].element_types == ["text"]
        assert result.pages[0].tables == []

    def test_仅表格无文本_页面正确标记(self):
        """页面仅有表格、无文本 → element_types 仅含 table"""
        page_table_only = _make_fitz_page("", tables=[MagicMock()])

        mock_doc = _make_fitz_doc([page_table_only])

        plumber_page = MagicMock()
        plumber_page.extract_tables.return_value = [[["A", "B"], ["1", "2"]]]

        mock_plumber = MagicMock()
        mock_plumber.pages = [plumber_page]

        with patch("app.rag.parser.fitz.open", return_value=mock_doc):
            with patch("app.rag.parser.pdfplumber.open", return_value=mock_plumber):
                result = _parse_pdf("table_only.pdf")

        assert result.failed_pages == 0
        assert result.pages[0].element_types == ["table"]
        assert len(result.pages[0].tables) == 1


class TestParseDocx:
    """DOCX 解析测试（Mock python-docx）"""

    def test_正常DOCX_逐段提取(self):
        mock_doc = MagicMock()
        mock_doc.paragraphs = [
            MagicMock(text="第一段内容"),
            MagicMock(text="第二段内容"),
        ]

        with patch("app.rag.parser.DocxDocument", return_value=mock_doc):
            result = _parse_docx("test.docx")

        assert result.total_pages == 2  # 逐段容错：每段一个 ParsedPage
        assert result.failed_pages == 0
        assert result.failure_rate == 0.0
        assert "第一段内容" in result.full_text
        assert "第二段内容" in result.full_text

    def test_空白段落被跳过_不影响容错率(self):
        mock_doc = MagicMock()
        mock_doc.paragraphs = [
            MagicMock(text="有效段落"),
            MagicMock(text=""),
            MagicMock(text="   "),
            MagicMock(text="另一有效段落"),
        ]

        with patch("app.rag.parser.DocxDocument", return_value=mock_doc):
            result = _parse_docx("test.docx")

        # 空白段落被跳过，不计入失败（仅计入 total_pages）
        assert result.total_pages == 4
        assert result.failed_pages == 0
        assert result.failure_rate == 0.0
        assert len(result.pages) == 2  # 仅有效段落创建 ParsedPage

    def test_DOCX全部空白_无有效文本(self):
        mock_doc = MagicMock()
        mock_doc.paragraphs = [
            MagicMock(text=""),
            MagicMock(text="   "),
        ]

        with patch("app.rag.parser.DocxDocument", return_value=mock_doc):
            result = _parse_docx("empty.docx")

        assert result.failed_pages == 2
        assert result.failure_rate == 1.0
        assert "无有效文本" in result.pages[0].error

    def test_DOCX单段解析异常_跳过继续(self):
        bad_para = MagicMock()
        type(bad_para).text = PropertyMock(side_effect=RuntimeError("段落损坏"))

        mock_doc = MagicMock()
        mock_doc.paragraphs = [
            MagicMock(text="正常段落"),
            bad_para,
            MagicMock(text="另一正常段落"),
        ]

        with patch("app.rag.parser.DocxDocument", return_value=mock_doc):
            result = _parse_docx("test.docx")

        assert result.failed_pages == 1
        assert result.total_pages == 3
        assert result.pages[0].success is True
        assert result.pages[2].success is True

    def test_DOCX文件损坏(self):
        with patch("app.rag.parser.DocxDocument", side_effect=ValueError("DOCX 文件损坏")):
            result = _parse_docx("corrupted.docx")

        assert result.failed_pages == 1
        assert result.failure_rate == 1.0
        assert "DOCX 文件损坏" in result.pages[0].error

    def test_DOCX无段落(self):
        mock_doc = MagicMock()
        mock_doc.paragraphs = []

        with patch("app.rag.parser.DocxDocument", return_value=mock_doc):
            result = _parse_docx("empty.docx")

        assert result.failed_pages == 1
        assert "无段落" in result.pages[0].error


class TestParseDocumentDispatch:
    """parse_document 入口分发测试"""

    def test_文件不存在(self):
        result = parse_document("/nonexistent/test.pdf")
        assert result.failed_pages == 1
        assert "不存在" in result.pages[0].error

    def test_不支持的文件类型(self, tmp_path):
        file_path = tmp_path / "test.xyz"
        file_path.write_text("test", encoding="utf-8")

        result = parse_document(str(file_path), "xyz")
        assert result.failed_pages == 1
        assert "不支持" in result.pages[0].error

    def test_从扩展名自动推断类型_txt(self, tmp_path):
        file_path = tmp_path / "readme.txt"
        file_path.write_text("Hello World", encoding="utf-8")

        result = parse_document(str(file_path))
        assert result.failed_pages == 0
        assert "Hello World" in result.full_text

    def test_从扩展名自动推断类型_md(self, tmp_path):
        file_path = tmp_path / "readme.md"
        file_path.write_text("# Hello", encoding="utf-8")

        result = parse_document(str(file_path))
        assert result.failed_pages == 0


class TestFaultToleranceThresholds:
    """容错阈值场景测试（对齐 ARCHITECTURE.md §4.7）— Mock pymupdf"""

    def test_5页PDF_1页失败_正好20pct(self):
        pages = [_make_fitz_page(f"第{i + 1}页") for i in range(4)]
        pages.append(_make_fitz_page(""))  # 第 5 页无文本
        mock_doc = _make_fitz_doc(pages)

        with patch("app.rag.parser.fitz.open", return_value=mock_doc):
            result = _parse_pdf("test.pdf")

        assert result.failure_rate == 0.2

    def test_3页PDF_1页失败_33pct_在20到50区间(self):
        page_bad = MagicMock()
        page_bad.get_text.side_effect = Exception("fail")
        page_bad.find_tables.return_value = []
        pages = [
            _make_fitz_page("OK"),
            page_bad,
            _make_fitz_page("OK"),
        ]
        mock_doc = _make_fitz_doc(pages)

        with patch("app.rag.parser.fitz.open", return_value=mock_doc):
            result = _parse_pdf("test.pdf")

        assert 0.2 < result.failure_rate < 0.5

    def test_2页PDF_1页失败_正好50pct(self):
        page_bad = MagicMock()
        page_bad.get_text.side_effect = Exception("fail")
        page_bad.find_tables.return_value = []
        pages = [
            _make_fitz_page("OK"),
            page_bad,
        ]
        mock_doc = _make_fitz_doc(pages)

        with patch("app.rag.parser.fitz.open", return_value=mock_doc):
            result = _parse_pdf("test.pdf")

        assert result.failure_rate == 0.5

    def test_2页PDF_全部失败_100pct(self):
        pages = [
            _make_fitz_page(""),
            _make_fitz_page(""),
        ]
        mock_doc = _make_fitz_doc(pages)

        with patch("app.rag.parser.fitz.open", return_value=mock_doc):
            result = _parse_pdf("test.pdf")

        assert result.failure_rate == 1.0


class TestTableToMarkdown:
    """_table_to_markdown 纯函数测试 — 表格数据 → Markdown 字符串"""

    def test_标准2列表格_完整Markdown输出(self):
        """标准表头+2行数据 → 正确 Markdown 表格"""
        data = [["姓名", "年龄"], ["张三", "30"], ["李四", "25"]]

        result = _table_to_markdown(data)

        lines = result.split("\n")
        assert len(lines) == 4  # 表头 + 分隔 + 2 数据行
        assert lines[0] == "| 姓名 | 年龄 |"
        assert lines[1] == "| --- | --- |"
        assert "| 张三 | 30 |" in result
        assert "| 李四 | 25 |" in result

    def test_3列表格含None单元格(self):
        """None 单元格 → 空字符串占位，列数按最大补齐"""
        data = [
            ["A", "B", "C"],
            ["1", None, "3"],
            [None, "2", None],
        ]

        result = _table_to_markdown(data)

        # 第 2 行第 2 列为空
        assert "| 1 |  | 3 |" in result
        # 第 3 行第 1、3 列为空
        assert "|  | 2 |  |" in result

    def test_空列表_返回空字符串(self):
        """输入 [] → 返回 "" """
        assert _table_to_markdown([]) == ""

    def test_单行表仅表头_返回空字符串(self):
        """仅一行表头无数据行 → 返回 "" """
        data = [["列1", "列2"]]
        assert _table_to_markdown(data) == ""

    def test_管道符转义和多行文本(self):
        """| 转义为 \\|，换行符替换为 <br>"""
        data = [
            ["名称", "描述"],
            ["A|B", "第一行\n第二行"],
        ]

        result = _table_to_markdown(data)

        assert "A\\|B" in result
        assert "第一行<br>第二行" in result

    def test_全空行被过滤(self):
        """表中包含全 None 空行 → 过滤掉"""
        data = [
            ["姓名", "年龄"],
            [None, None],
            ["张三", "30"],
        ]

        result = _table_to_markdown(data)

        lines = result.split("\n")
        # 应只有 3 行：表头 + 分隔 + 1 数据行
        assert len(lines) == 3

    def test_列数不一致自动补齐(self):
        """不同行列数不一致 → 按最大列数补齐空白列"""
        data = [
            ["A", "B", "C"],
            ["1", "2"],  # 少一列
        ]

        result = _table_to_markdown(data)

        assert "| 1 | 2 |  |" in result


class TestParsePdfWithPlumber:
    """_parse_pdf_with_pdfplumber 降级模式测试"""

    def test_降级模式_正常逐页提取(self):
        """pdfplumber 降级模式：逐页 extract_text"""
        plumber_pages = [
            _make_pdfplumber_page("降级页1"),
            _make_pdfplumber_page("降级页2"),
        ]
        mock_plumber = MagicMock()
        mock_plumber.pages = plumber_pages

        with patch("app.rag.parser.pdfplumber.open", return_value=mock_plumber):
            result = _parse_pdf_with_pdfplumber("test.pdf")

        assert result.total_pages == 2
        assert result.failed_pages == 0
        assert result.pages[0].content == "降级页1"
        assert result.pages[1].content == "降级页2"

    def test_降级模式_部分页面无文本(self):
        """降级模式下空页面 → 标记失败"""
        plumber_pages = [
            _make_pdfplumber_page("OK"),
            _make_pdfplumber_page(""),
        ]
        mock_plumber = MagicMock()
        mock_plumber.pages = plumber_pages

        with patch("app.rag.parser.pdfplumber.open", return_value=mock_plumber):
            result = _parse_pdf_with_pdfplumber("test.pdf")

        assert result.failed_pages == 1
        assert not result.pages[1].success

    def test_降级模式_pdfplumber也失败(self):
        """两引擎均失败 → error 包含双方信息"""
        with patch("app.rag.parser.pdfplumber.open", side_effect=RuntimeError("plumber 失败")):
            result = _parse_pdf_with_pdfplumber("bad.pdf", original_error="fitz 失败")

        assert result.failed_pages == 1
        assert "fitz 失败" in result.pages[0].error
        assert "plumber 失败" in result.pages[0].error
