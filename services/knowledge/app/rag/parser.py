"""文档解析 — 使用 pymupdf + pdfplumber + python-docx 逐页/逐段提取文本，支持部分容错

对齐 ARCHITECTURE.md §4.7:
- 单页/单段失败跳过并记录 warning
- < 20% 失败 → 继续（记录 warning）
- 20%~50% 失败 → partial_failed
- > 50% 失败 → failed

对齐 ROADMAP.md §8.7（Chunk 元数据增强）：
- DOCX 标题样式自动转换为 Markdown # 标记，使 chunker 的标题检测跨格式统一

PDF 解析引擎（对齐 ADR-025）：
- pymupdf (fitz) 主力文本提取，中文支持优于 PyPDF2
- pdfplumber 按需表格提取（仅 pymupdf 检测到表格的页面）
- pymupdf 打开失败时 pdfplumber 全量降级
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz
import pdfplumber
from docx import Document as DocxDocument
from docx.enum.style import WD_STYLE_TYPE
from pdfplumber.pdf import PDF

logger = logging.getLogger(__name__)

# Word 内置标题样式名映射 -> Markdown 标题层级
_WORD_HEADING_PATTERN = re.compile(r"^Heading\s*(\d+)", re.IGNORECASE)
_WORD_TITLE_PATTERNS = re.compile(r"^(Title|Subtitle)$", re.IGNORECASE)


@dataclass
class ParsedPage:
    """单页解析结果"""

    page_number: int
    content: str
    success: bool = True
    error: str | None = None
    element_types: list[str] = field(default_factory=list)  # ["text", "table"]
    tables: list[str] = field(default_factory=list)  # Markdown 表格文本


@dataclass
class ParseResult:
    """文档解析聚合结果"""

    pages: list[ParsedPage] = field(default_factory=list)
    total_pages: int = 0
    failed_pages: int = 0
    source_type: str = ""  # pdf / docx / md / txt，用于日志单位判断

    @property
    def failure_rate(self) -> float:
        if self.total_pages == 0:
            return 1.0  # 空文档视为全部失败
        return self.failed_pages / self.total_pages

    @property
    def full_text(self) -> str:
        """拼接所有成功页面的文本"""
        return "\n\n".join(p.content for p in self.pages if p.success)

    @property
    def warnings(self) -> list[str]:
        """收集所有失败页面的警告信息"""
        return [f"第{p.page_number}页: {p.error}" for p in self.pages if not p.success and p.error]


def parse_document(file_path: str, file_type: str | None = None) -> ParseResult:
    """解析文档主入口，根据文件类型分发到对应解析器。

    Args:
        file_path: 文档文件绝对路径
        file_type: 文件类型（pdf/docx/md/txt），为 None 时从扩展名推断

    Returns:
        ParseResult: 包含逐页/逐段解析结果和容错统计
    """
    path = Path(file_path)
    if not path.exists():
        return ParseResult(
            pages=[
                ParsedPage(
                    page_number=1, content="", success=False, error=f"文件不存在: {file_path}"
                )
            ],
            total_pages=1,
            failed_pages=1,
            source_type=file_type or "",
        )

    if file_type is None:
        file_type = path.suffix.lower().lstrip(".")

    try:
        if file_type == "pdf":
            result = _parse_pdf(file_path)
        elif file_type == "docx":
            result = _parse_docx(file_path)
        elif file_type in ("md", "txt"):
            result = _parse_text(file_path)
        else:
            return ParseResult(
                pages=[
                    ParsedPage(
                        page_number=1,
                        content="",
                        success=False,
                        error=f"不支持的文件类型: {file_type}",
                    )
                ],
                total_pages=1,
                failed_pages=1,
                source_type=file_type,
            )
        result.source_type = file_type
        return result
    except Exception as e:
        logger.exception(f"文档解析异常: {file_path}")
        return ParseResult(
            pages=[ParsedPage(page_number=1, content="", success=False, error=str(e))],
            total_pages=1,
            failed_pages=1,
            source_type=file_type or "",
        )


def _table_to_markdown(table_data: list[list[str | None]]) -> str:
    """将 pdfplumber 原始表格数据转换为 GitHub-flavored Markdown 表格。

    纯函数。对齐 ADR-025：表格嵌入 page.content 为 Markdown 字符串，
    chunker 的 RecursiveCharacterTextSplitter 自然在表格边界切分。

    处理规则：
    - None 单元格 → 空字符串
    - 多行文本 → <br> 替换换行
    - 管道符 | → \\| 转义
    - 空表（无数据）或单行表（仅表头无数据行）→ 返回空字符串
    - 列数不一致时按最大列数补齐

    Args:
        table_data: pdfplumber page.extract_tables() 返回的单表数据

    Returns:
        GitHub-flavored Markdown 表格字符串，或空字符串
    """
    if not table_data or len(table_data) == 0:
        return ""

    # 过滤全空行（所有单元格均为 None 或空字符串）
    rows: list[list[str | None]] = []
    for row in table_data:
        if row and any(cell is not None and str(cell).strip() for cell in row):
            rows.append(row)

    if not rows:
        return ""

    # 仅表头无数据行 → 返回空字符串
    if len(rows) < 2:
        return ""

    # 确定最大列数
    max_cols = max(len(row) for row in rows)
    if max_cols == 0:
        return ""

    # 标准化：补齐列数，None → ""
    normalized: list[list[str]] = []
    for row in rows:
        padded = list(row) + [""] * (max_cols - len(row))
        normalized.append([str(cell) if cell is not None else "" for cell in padded])

    def _clean_cell(text: str) -> str:
        """转义管道符、换行转 <br>、去首尾空白"""
        text = text.replace("\\", "\\\\")
        text = text.replace("|", "\\|")
        text = text.replace("\n", "<br>")
        return text.strip()

    cleaned = [[_clean_cell(cell) for cell in row] for row in normalized]

    # 构建 Markdown 表格
    lines: list[str] = []
    # 表头
    lines.append("| " + " | ".join(cleaned[0]) + " |")
    # 分隔行
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    # 数据行
    for cleaned_row in cleaned[1:]:
        lines.append("| " + " | ".join(cleaned_row) + " |")

    return "\n".join(lines)


def _parse_pdf(file_path: str) -> ParseResult:
    """使用 pymupdf 主力 + pdfplumber 按需表格提取解析 PDF。

    引擎协作策略（对齐 ADR-025）：
    1. pymupdf (fitz) 主力文本提取
    2. page.find_tables() 检测表格 → 按需打开 pdfplumber 提取该页表格
    3. pymupdf 打开失败 → pdfplumber 全量降级
    4. 表格渲染为 Markdown 嵌入 page.content
    """
    # === 主力引擎：pymupdf ===
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        return _parse_pdf_with_pdfplumber(file_path, original_error=str(e))

    pages: list[ParsedPage] = []
    failed = 0
    pdfplumber_doc: PDF | None = None  # 按需懒加载
    pdfplumber_unavailable = False

    for i in range(len(doc)):
        try:
            page = doc[i]
            text = page.get_text("text")

            # 表格检测
            table_md_list: list[str] = []
            try:
                fitz_tables = page.find_tables()
            except Exception:
                fitz_tables = None

            if fitz_tables:
                # 按需打开 pdfplumber
                if pdfplumber_doc is None and not pdfplumber_unavailable:
                    try:
                        pdfplumber_doc = pdfplumber.open(file_path)
                    except Exception:
                        pdfplumber_unavailable = True

                if pdfplumber_doc is not None and i < len(pdfplumber_doc.pages):
                    try:
                        plumber_page = pdfplumber_doc.pages[i]
                        extracted_tables = plumber_page.extract_tables()
                        if extracted_tables:
                            for table_data in extracted_tables:
                                md = _table_to_markdown(table_data)
                                if md:
                                    table_md_list.append(md)
                    except Exception as exc:
                        logger.warning(f"pdfplumber 第{i + 1}页表格提取失败: {exc}")

            # 组装 content：文本 + 表格
            content_parts: list[str] = []
            if text and text.strip():
                content_parts.append(text.strip())
            content_parts.extend(table_md_list)

            content = "\n\n".join(content_parts)

            if content:
                element_types = ["text"] if (text and text.strip()) else []
                if table_md_list:
                    element_types.append("table")
                pages.append(
                    ParsedPage(
                        page_number=i + 1,
                        content=content,
                        element_types=element_types,
                        tables=table_md_list,
                    )
                )
            else:
                pages.append(
                    ParsedPage(
                        page_number=i + 1, content="", success=False, error="页面无文本或文本为空"
                    )
                )
                failed += 1
        except Exception as e:
            pages.append(
                ParsedPage(page_number=i + 1, content="", success=False, error=f"页面解析异常: {e}")
            )
            failed += 1

    total = len(doc)

    if pdfplumber_doc is not None:
        try:
            pdfplumber_doc.close()
        except Exception:
            pass
    try:
        doc.close()
    except Exception:
        pass

    return ParseResult(pages=pages, total_pages=total, failed_pages=failed)


def _parse_pdf_with_pdfplumber(file_path: str, original_error: str = "") -> ParseResult:
    """pymupdf 无法打开文件时的 pdfplumber 全量降级模式。

    仅做纯文本提取，不检测表格（降级模式优先保证文本不丢失）。
    """
    try:
        doc = pdfplumber.open(file_path)
    except Exception as e:
        error_msg = (
            f"pymupdf 失败: {original_error}; pdfplumber 失败: {e}" if original_error else str(e)
        )
        return ParseResult(
            pages=[ParsedPage(page_number=1, content="", success=False, error=error_msg)],
            total_pages=1,
            failed_pages=1,
        )

    pages: list[ParsedPage] = []
    failed = 0

    for i, page in enumerate(doc.pages):
        try:
            text = page.extract_text()
            if text and text.strip():
                pages.append(ParsedPage(page_number=i + 1, content=text.strip()))
            else:
                pages.append(
                    ParsedPage(
                        page_number=i + 1, content="", success=False, error="页面无文本或文本为空"
                    )
                )
                failed += 1
        except Exception as e:
            pages.append(
                ParsedPage(page_number=i + 1, content="", success=False, error=f"页面解析异常: {e}")
            )
            failed += 1

    total = len(doc.pages)
    try:
        doc.close()
    except Exception:
        pass
    return ParseResult(pages=pages, total_pages=total, failed_pages=failed)


def _docx_heading_to_markdown(paragraph) -> str | None:
    """检测 Word 段落是否为标题样式，返回对应的 Markdown # 前缀文本。

    对齐 ROADMAP.md §8.7：将 DOCX 标题样式转换为 Markdown 标记，
    使 chunker.py 的 detect_sections() 可跨 MD/DOCX 统一检测。

    防御性设计：MagicMock 等非真实对象会导致属性访问异常，
    此时返回 None 降级为普通文本提取。

    Args:
        paragraph: python-docx Paragraph 对象

    Returns:
        带 # 前缀的标题文本，或 None（非标题段落/异常）
    """
    try:
        style = paragraph.style
        if style is None:
            return None

        text = paragraph.text
        if not text or not text.strip():
            return None

        # 检查段落样式（优先）
        style_name = style.name or ""
        m = _WORD_HEADING_PATTERN.match(style_name)
        if m:
            level = int(m.group(1))
            if 1 <= level <= 6:
                return f"{'#' * level} {text.strip()}"

        # Title/Subtitle → # / ##
        if _WORD_TITLE_PATTERNS.match(style_name):
            if style_name.lower() == "title":
                return f"# {text.strip()}"
            else:
                return f"## {text.strip()}"

        # 检查大纲级别（Word 内置段落属性 outline_level，如 outlineLvl）
        try:
            outline_lvl = paragraph.paragraph_format.outline_level
            if outline_lvl is not None and 0 <= outline_lvl <= 5:
                return f"{'#' * (outline_lvl + 1)} {text.strip()}"
        except (AttributeError, ValueError, TypeError):
            pass

        # 检查段落样式类型是否为 HEADING
        if style.type == WD_STYLE_TYPE.PARAGRAPH and hasattr(style, "base_style"):
            try:
                base = style.base_style
                if base is not None:
                    base_name = base.name or ""
                    m2 = _WORD_HEADING_PATTERN.match(base_name)
                    if m2:
                        level = int(m2.group(1))
                        if 1 <= level <= 6:
                            return f"{'#' * level} {text.strip()}"
            except (AttributeError, ValueError, TypeError):
                pass

        return None
    except (AttributeError, TypeError, ValueError):
        # MagicMock 等非真实对象 → 降至普通文本
        return None


def _parse_docx(file_path: str) -> ParseResult:
    """使用 python-docx 解析 DOCX，逐段提取并容错（对齐 PDF 逐页容错粒度）。

    DOCX 标题样式自动转换为 Markdown # 标记，使 chunker.py 的章节检测
    跨 MD/DOCX 格式统一工作（对齐 ROADMAP.md §8.7）。
    """
    try:
        doc = DocxDocument(file_path)
    except Exception as e:
        return ParseResult(
            pages=[ParsedPage(page_number=1, content="", success=False, error=str(e))],
            total_pages=1,
            failed_pages=1,
        )

    if not doc.paragraphs:
        return ParseResult(
            pages=[ParsedPage(page_number=1, content="", success=False, error="文档无段落内容")],
            total_pages=1,
            failed_pages=1,
        )

    pages: list[ParsedPage] = []
    failed = 0

    for i, p in enumerate(doc.paragraphs):
        try:
            # 检测标题样式，转换为 Markdown 标记（§8.7）
            heading_text = _docx_heading_to_markdown(p)
            if heading_text is not None:
                pages.append(ParsedPage(page_number=i + 1, content=heading_text))
            else:
                text = p.text
                if text and text.strip():
                    pages.append(ParsedPage(page_number=i + 1, content=text.strip()))
        except Exception as e:
            logger.warning(f"DOCX 第{i + 1}段解析失败: {e}")
            pages.append(
                ParsedPage(page_number=i + 1, content="", success=False, error=f"段落解析异常: {e}")
            )
            failed += 1

    total = len(doc.paragraphs)

    if not pages:
        return ParseResult(
            pages=[
                ParsedPage(page_number=1, content="", success=False, error="文档无有效文本内容")
            ],
            total_pages=total,
            failed_pages=total,
        )

    return ParseResult(pages=pages, total_pages=total, failed_pages=failed)


def _parse_text(file_path: str) -> ParseResult:
    """解析纯文本文件（md/txt），统一 UTF-8 读取"""
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = Path(file_path).read_text(encoding="gbk")
        except Exception as e:
            return ParseResult(
                pages=[
                    ParsedPage(page_number=1, content="", success=False, error=f"编码错误: {e}")
                ],
                total_pages=1,
                failed_pages=1,
            )
    except Exception as e:
        return ParseResult(
            pages=[ParsedPage(page_number=1, content="", success=False, error=str(e))],
            total_pages=1,
            failed_pages=1,
        )

    if not content.strip():
        return ParseResult(
            pages=[ParsedPage(page_number=1, content="", success=False, error="文件内容为空")],
            total_pages=1,
            failed_pages=1,
        )

    page = ParsedPage(page_number=1, content=content.strip())
    return ParseResult(pages=[page], total_pages=1, failed_pages=0)
