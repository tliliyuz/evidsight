"""RAG 入库数据清洗 — 页眉页脚/页号去噪 + 空白/空行规整 + 损坏 Unicode 修复

对齐 M2 数据清洗优化（ROADMAP.md §M2 范围内工作）：在 parse 与 chunk 之间
插入确定性的 Clean 阶段，清洗 PDF/DOCX/Markdown 解析文本中的常见噪声源。

清洗作用于**页面结构**而非拼接后的 full_text：ParseResult.full_text 是派生属性
（"\\n\\n".join(p.content)），chunker.build_page_offset_map 重走同样的 p.content
重建 offset→page 映射。逐页清洗后 full_text 自动从清洗后的页面重新派生，
字符偏移不变式自然保持。

范围（负责人确认）：
- 页眉页脚/页号去噪（仅删边界页号行，不动正文）
- 空白/空行规整 + 安全折行拼接（修复 PDF 断行）
- 损坏 Unicode 修复（U+FFFD / mojibake / 全半角）

明确不做（后续切片）：引用/目录噪声过滤、近重复 chunk 去重、水印剥离、LLM 清洗。

所有函数为纯函数、确定性、无 I/O、可单测。逐项开关在接线层由 config 控制。
"""

from __future__ import annotations

import re

from app.rag.parser import ParseResult

logger = __import__("logging").getLogger(__name__)

# 句末标点：出现在这些字符后不拼接断行（保留句子边界）
_SENTENCE_TERMINATORS = ("。", "！", "？", ".", "!", "?")

# 页号行：纯数字，或由 - · # 等符号包裹的数字，或"第 N 页"
_PAGE_NUMBER_RE = re.compile(
    r"^(?:\s*[-·.．#]?\s*\d+\s*[-·.．#]?\s*)$"
    r"|^(?:第\s*\d+\s*页)$"
)

# Markdown ATX 标题行（行首 # 开头），避免把标题拼进正文破坏章节检测
_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")

# 编号列表项（数字后跟 .、.、) 、、等），避免拼接破坏列表
_NUMBERED_ITEM_RE = re.compile(r"^\s*\d+[\.、．\))\s]")


# ==================== 1. 页眉页脚/页号 ====================


def is_page_number_only(line: str) -> bool:
    """判定一行是否为纯页号/页码行。

    识别：纯数字（"42"）、符号包裹数字（"- 12 -"、"· 12 ·"）、中文页码（"第 12 页"）。
    正文行（含数字的句子、编号列表项）不算页号。
    """
    stripped = line.strip()
    if not stripped:
        return False
    return bool(_PAGE_NUMBER_RE.match(stripped))


def strip_page_boilerplate(content: str) -> str:
    """删除页面首尾的纯页号/页码行，不动正文。

    保守策略：只移除位于页面内容最前/最后的页号行；正文中夹着的数字行不处理。
    """
    lines = content.split("\n")

    # 删除开头的连续页号行
    start = 0
    while start < len(lines) and is_page_number_only(lines[start]):
        start += 1

    # 删除结尾的连续页号行
    end = len(lines)
    while end > start and is_page_number_only(lines[end - 1]):
        end -= 1

    return "\n".join(lines[start:end])


# ==================== 2. 空白/空行规整 ====================


def normalize_whitespace(text: str) -> str:
    """空白规整：折叠连续水平空白（含全角空格 U+3000）为单空格、去行尾空格、
    三个以上连续空行并为一个空行、去除首尾空行、CRLF 归一为 LF。

    保留单个换行符（页面内行结构），只有连续的空白行被折叠。
    """
    # CRLF/CR → LF
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = text.split("\n")
    out: list[str] = []
    blank_run = 0

    for line in lines:
        # 折叠行内连续水平空白为单空格，再去掉行尾空格
        collapsed = re.sub(r"[ \t　]+", " ", line).rstrip(" ")
        if not collapsed.strip():
            # 空行：连续空行只保留一个空行（一次）
            if blank_run == 0:
                out.append("")
            blank_run += 1
        else:
            blank_run = 0
            out.append(collapsed)

    # 去除首尾空行
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()

    return "\n".join(out)


def _ends_with_sentence_terminator(line: str) -> bool:
    """行尾是否为句末标点（决定该行是否可向后拼接断行）"""
    stripped = line.rstrip()
    return stripped.endswith(_SENTENCE_TERMINATORS)


def _is_markdown_heading(line: str) -> bool:
    return bool(_MD_HEADING_RE.match(line))


def _is_numbered_item(line: str) -> bool:
    return bool(_NUMBERED_ITEM_RE.match(line))


def join_wrapped_lines(text: str) -> str:
    """安全折行拼接：修复 PDF 文本提取的行尾断行。

    规则：若前一行不以句末标点结尾、不是 Markdown 标题行、不是编号列表项，
    且后一行非空，则将后一行拼接到前一行行尾（去掉换行）。
    空行段落分隔保持不变。
    """
    if not text:
        return ""

    lines = text.split("\n")
    result: list[str] = []

    for line in lines:
        if not line.strip():
            # 空行是段落分隔，独立保留
            result.append(line)
            continue

        if (
            result
            and result[-1].strip()
            and not _ends_with_sentence_terminator(result[-1])
            and not _is_markdown_heading(result[-1])
            and not _is_numbered_item(result[-1])
        ):
            result[-1] = result[-1] + line.strip()
        else:
            result.append(line)

    return "\n".join(result)


# ==================== 3. 损坏 Unicode 修复 ====================


def _fullwidth_to_halfwidth(text: str) -> str:
    """全角 ASCII 字符归一为半角（U+FF01–U+FF5E → U+21–U+7E）"""
    result: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        elif code == 0x3000:  # 全角空格 → 半角空格（交由 normalize_whitespace 折叠）
            result.append(" ")
        else:
            result.append(ch)
    return "".join(result)


def _repair_mojibake(text: str) -> str:
    """修复常见的 latin-1/cp1252 误解码 mojibake。

    启发式：对文本中每一段「可 latin-1 编码」的连续字符做无损回编
    （latin-1 编码 → utf-8 解码）。只有该段确实因此发生变化且不引入替换符
    时才采纳。CJK/emoji 等字符天然不可 latin-1 编码，按边界原样保留，
    因此混排文本中只有真正的 mojibake 片段被修复，已正确的内容不受影响。
    """
    # 仅当存在非 ASCII 字符时尝试，纯 ASCII 文本直接跳过
    if not any(ord(ch) > 127 for ch in text):
        return text

    def _repair_segment(segment: str) -> str:
        if not segment or not any(ord(ch) > 127 for ch in segment):
            return segment
        try:
            repaired = segment.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return segment
        # 修复结果不得引入替换符；且需确实发生了变化
        if "�" in repaired or repaired == segment:
            return segment
        return repaired

    out: list[str] = []
    buf: list[str] = []
    for ch in text:
        if ord(ch) <= 0xFF:  # 可 latin-1 编码，收集到当前片段
            buf.append(ch)
        else:
            if buf:
                out.append(_repair_segment("".join(buf)))
                buf = []
            out.append(ch)  # CJK/emoji 等作为边界，原样保留
    if buf:
        out.append(_repair_segment("".join(buf)))
    return "".join(out)


def repair_broken_unicode(text: str) -> str:
    """损坏 Unicode 修复：移除 U+FFFD 替换符、修复 latin-1 误解码 mojibake、全角归一半角。"""
    text = text.replace("�", "")
    text = _fullwidth_to_halfwidth(text)
    text = _repair_mojibake(text)
    return text


# ==================== 组合管线 ====================


def clean_text(
    text: str, *, normalize_space: bool = True, repair_unicode: bool = True
) -> str:
    """单段文本确定性清洗管线。

    顺序敏感：先修复 Unicode（避免 mojibake 在空白折叠时被粘合），
    再规整空白，最后安全拼接断行。

    Args:
        text: 待清洗文本
        normalize_space: 空白规整 + 安全折行拼接开关（对齐 CLEAN_NORMALIZE_WHITESPACE）
        repair_unicode: 损坏 Unicode 修复开关（对齐 CLEAN_REPAIR_UNICODE）
    """
    if repair_unicode:
        text = repair_broken_unicode(text)
    if normalize_space:
        text = normalize_whitespace(text)
        text = join_wrapped_lines(text)
    return text


def clean_parse_result(
    result: ParseResult,
    *,
    strip_boilerplate: bool = True,
    normalize_space: bool = True,
    repair_unicode: bool = True,
    mode: str | None = None,
) -> ParseResult:
    """对 ParseResult 逐成功页执行清洗，返回新的 ParseResult（不改入参）。

    清洗顺序：页号/页眉页脚去噪 → Unicode 修复 → 空白规整 → 折行拼接。
    失败页保留原样。total_pages / failed_pages / source_type 原样保留，
    因此 full_text 与 chunker.build_page_offset_map 的偏移映射保持一致。

    Args:
        result: 解析结果
        strip_boilerplate: 页号/页眉页脚去噪开关（对齐 CLEAN_STRIP_BOILERPLATE）
        normalize_space: 空白规整 + 安全折行拼接开关（对齐 CLEAN_NORMALIZE_WHITESPACE）
        repair_unicode: 损坏 Unicode 修复开关（对齐 CLEAN_REPAIR_UNICODE）
        mode: 保留参数，供未来扩展清洗策略；当前实现与 None 等价
    """
    cleaned_pages = []
    for page in result.pages:
        if not page.success or not page.content:
            cleaned_pages.append(page)
            continue

        content = page.content
        if strip_boilerplate:
            content = strip_page_boilerplate(content)
        content = clean_text(
            content, normalize_space=normalize_space, repair_unicode=repair_unicode
        )
        cleaned_pages.append(
            type(page)(
                page_number=page.page_number,
                content=content,
                success=page.success,
                error=page.error,
                element_types=page.element_types,
                tables=page.tables,
            )
        )

    return ParseResult(
        pages=cleaned_pages,
        total_pages=result.total_pages,
        failed_pages=result.failed_pages,
        source_type=result.source_type,
    )
