"""文档摄入与知识规范化流水线。

流程：清洗去噪 → 结构还原为 Markdown → 语义分块 → 元数据抽取。
输出两种中间表示：Markdown（展示/溯源）与知识单元列表（入库/检索）。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from langchain_core.documents import Document

from config import CHUNK_OVERLAP, CHUNK_SIZE

PARSER_VERSION = "v1.2"

_PAGE_MARKER = re.compile(r"<!--\s*page:\s*(\d+)\s*-->", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_CODE_FENCE = re.compile(r"^```")
_TABLE_LINE = re.compile(r"^\|.*\|$")
_LIST_LINE = re.compile(r"^(\s*[-*+]|\s*\d+\.)\s+")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_WATERMARK = re.compile(
    r"(?im)^(?:confidential|内部资料|仅供内部使用|勿外传|watermark|版权所有).*$"
)
_REPEATED_BLANK = re.compile(r"\n{3,}")
_REPEATED_SPACE = re.compile(r"[ \t]{2,}")
_HEADER_FOOTER_LINE = re.compile(
    r"(?im)^(?:第\s*\d+\s*页(?:\s*/\s*共\s*\d+\s*页)?|page\s+\d+(?:\s+of\s+\d+)?|-+\s*\d+\s*-+)\s*$"
)


@dataclass
class KnowledgeUnit:
    chunk_id: str
    user_id: int
    doc_id: int
    folder_id: int
    source: str
    page: int | None
    heading_path: list[str]
    content: str
    content_type: str
    parser_version: str = PARSER_VERSION
    chunk_index: int = 0

    def to_jsonl(self) -> str:
        payload = asdict(self)
        return json.dumps(payload, ensure_ascii=False)


@dataclass
class NormalizedDocument:
    markdown: str
    jsonl: str
    units: list[KnowledgeUnit] = field(default_factory=list)


def clean_text(text: str) -> str:
    """清洗去噪：控制字符、水印行、页眉页脚、重复空行。"""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _CONTROL_CHARS.sub("", cleaned)
    cleaned = cleaned.replace("\ufeff", "").replace("\u200b", "")
    lines = []
    for line in cleaned.split("\n"):
        stripped = line.strip()
        if _WATERMARK.match(stripped) or _HEADER_FOOTER_LINE.match(stripped):
            continue
        lines.append(line.rstrip())
    cleaned = "\n".join(lines)
    cleaned = _REPEATED_BLANK.sub("\n\n", cleaned)
    cleaned = "\n".join(_REPEATED_SPACE.sub(" ", line) for line in cleaned.split("\n"))
    return cleaned.strip()


def documents_to_markdown(documents: list[Document], filename: str) -> str:
    """把解析结果还原为带结构的 Markdown，并保留页码标记。"""
    parts: list[str] = []
    for document in documents:
        content = clean_text(document.page_content or "")
        if not content:
            continue
        page = document.metadata.get("page")
        if page is not None:
            try:
                parts.append(f"<!-- page: {int(page) + 1} -->")
            except (TypeError, ValueError):
                pass
        parts.append(content)
    markdown = clean_text("\n\n".join(parts))
    if not markdown:
        return ""
    # 纯文本文件若无标题，用文件名补一层，便于语义分块与溯源
    if not any(line.startswith("#") for line in markdown.splitlines()):
        stem = Path(filename).stem.strip() or filename
        markdown = f"# {stem}\n\n{markdown}"
    return markdown


def detect_content_type(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return "text"
    if any(line.strip().startswith("```") for line in lines):
        return "code"
    table_lines = sum(1 for line in lines if _TABLE_LINE.match(line.strip()))
    if table_lines >= 2 and table_lines >= len(lines) * 0.5:
        return "table"
    list_lines = sum(1 for line in lines if _LIST_LINE.match(line))
    if list_lines >= 2 and list_lines >= len(lines) * 0.5:
        return "list"
    return "text"


def _split_blocks(markdown: str) -> list[dict]:
    """按标题/段落/表格/列表/代码块切成结构块。"""
    lines = markdown.splitlines()
    blocks: list[dict] = []
    buffer: list[str] = []
    page: int | None = None
    heading_stack: list[tuple[int, str]] = []
    in_code = False
    block_page = page

    def heading_path() -> list[str]:
        return [title for _, title in heading_stack]

    def flush(kind: str) -> None:
        nonlocal buffer, block_page
        text = "\n".join(buffer).strip()
        buffer = []
        if not text:
            block_page = page
            return
        blocks.append(
            {
                "content": text,
                "content_type": kind,
                "heading_path": heading_path(),
                "page": block_page,
            }
        )
        block_page = page

    def current_kind(line: str) -> str:
        if in_code or _CODE_FENCE.match(line.strip()):
            return "code"
        if _TABLE_LINE.match(line.strip()):
            return "table"
        if _LIST_LINE.match(line):
            return "list"
        return "text"

    active_kind: str | None = None
    for raw in lines:
        page_match = _PAGE_MARKER.match(raw.strip())
        if page_match and not in_code:
            if buffer:
                flush(active_kind or "text")
                active_kind = None
            page = int(page_match.group(1))
            block_page = page
            continue

        stripped = raw.strip()
        if _CODE_FENCE.match(stripped):
            if not in_code:
                if buffer:
                    flush(active_kind or "text")
                in_code = True
                active_kind = "code"
                buffer = [raw]
            else:
                buffer.append(raw)
                flush("code")
                in_code = False
                active_kind = None
            continue

        if in_code:
            buffer.append(raw)
            continue

        heading = _HEADING.match(stripped)
        if heading:
            if buffer:
                flush(active_kind or "text")
                active_kind = None
            level = len(heading.group(1))
            title = heading.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            blocks.append(
                {
                    "content": stripped,
                    "content_type": "heading",
                    "heading_path": heading_path(),
                    "page": page,
                }
            )
            continue

        if not stripped:
            if buffer and active_kind in {"text", "list"}:
                flush(active_kind)
                active_kind = None
            elif buffer and active_kind == "table":
                # 表格空行结束
                flush("table")
                active_kind = None
            continue

        kind = current_kind(raw)
        if active_kind and kind != active_kind:
            flush(active_kind)
            active_kind = None
        active_kind = kind
        buffer.append(raw)

    if buffer:
        flush(active_kind or "text")
    return blocks


def _pack_blocks(
    blocks: list[dict],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict]:
    """把结构块组装为带重叠的语义分块。"""
    chunks: list[dict] = []
    current: list[dict] = []
    current_len = 0

    def emit(parts: list[dict]) -> None:
        if not parts:
            return
        body_parts = [part["content"] for part in parts if part["content_type"] != "heading"]
        if not body_parts:
            return
        # 块首补最近标题路径，检索后半段时仍可知章节
        heading_path = parts[-1]["heading_path"]
        prefix = ""
        if heading_path and not body_parts[0].lstrip().startswith("#"):
            prefix = "# " + " / ".join(heading_path) + "\n"
        content = prefix + "\n\n".join(body_parts)
        content = clean_text(content)
        if not content:
            return
        pages = [part["page"] for part in parts if part.get("page") is not None]
        types = {part["content_type"] for part in parts if part["content_type"] != "heading"}
        content_type = "text"
        if types == {"table"}:
            content_type = "table"
        elif types == {"list"}:
            content_type = "list"
        elif types == {"code"}:
            content_type = "code"
        elif len(types) == 1:
            content_type = next(iter(types))
        chunks.append(
            {
                "content": content,
                "heading_path": heading_path,
                "page": pages[0] if pages else None,
                "content_type": content_type,
            }
        )

    def overlap_tail(parts: list[dict]) -> list[dict]:
        if not parts or chunk_overlap <= 0:
            return []
        kept: list[dict] = []
        size = 0
        for part in reversed(parts):
            if part["content_type"] == "heading":
                continue
            length = len(part["content"])
            if kept and size + length > chunk_overlap:
                break
            kept.append(part)
            size += length
            if size >= chunk_overlap:
                break
        kept.reverse()
        return kept

    for block in blocks:
        text = block["content"]
        length = len(text)

        if block["content_type"] == "heading":
            if current and current_len > chunk_size * 0.6:
                emit(current)
                current = overlap_tail(current)
                current_len = sum(len(item["content"]) for item in current)
            current.append(block)
            continue

        if length > chunk_size:
            if current:
                emit(current)
                current = overlap_tail(current)
                current_len = sum(len(item["content"]) for item in current)
            # 超大块按重叠硬切，尽量在句号处断开
            start = 0
            while start < length:
                end = min(start + chunk_size, length)
                if end < length:
                    window = text[start:end]
                    for sep in ("。", "！", "？", "\n", "；", ". ", "! ", "? "):
                        pos = window.rfind(sep)
                        if pos >= chunk_size // 3:
                            end = start + pos + len(sep)
                            break
                piece = text[start:end].strip()
                if piece:
                    emit(
                        [
                            {
                                **block,
                                "content": piece,
                            }
                        ]
                    )
                if end >= length:
                    break
                start = max(end - chunk_overlap, start + 1)
            current = []
            current_len = 0
            continue

        if current and current_len + length + 2 > chunk_size and any(
            item["content_type"] != "heading" for item in current
        ):
            emit(current)
            current = overlap_tail(current)
            current_len = sum(len(item["content"]) for item in current)

        current.append(block)
        current_len += length + 2

    emit(current)
    return chunks


def semantic_chunk(
    markdown: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    blocks = _split_blocks(markdown)
    if not blocks:
        return []
    return _pack_blocks(blocks, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def build_knowledge_units(
    markdown: str,
    *,
    user_id: int,
    doc_id: int,
    folder_id: int,
    source: str,
    folder_key: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> NormalizedDocument:
    """规范化输出：Markdown + JSONL 知识单元。"""
    cleaned = clean_text(markdown)
    chunks = semantic_chunk(cleaned, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    units: list[KnowledgeUnit] = []
    for index, chunk in enumerate(chunks):
        unit = KnowledgeUnit(
            chunk_id=f"{folder_key}_doc{doc_id}_chunk_{index}",
            user_id=user_id,
            doc_id=doc_id,
            folder_id=folder_id,
            source=source,
            page=chunk.get("page"),
            heading_path=list(chunk.get("heading_path") or []),
            content=chunk["content"],
            content_type=chunk.get("content_type") or detect_content_type(chunk["content"]),
            parser_version=PARSER_VERSION,
            chunk_index=index,
        )
        units.append(unit)
    jsonl = "\n".join(unit.to_jsonl() for unit in units)
    return NormalizedDocument(markdown=cleaned, jsonl=jsonl, units=units)
