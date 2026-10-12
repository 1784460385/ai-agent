import json
import os
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from openpyxl import load_workbook
from pptx import Presentation


class ParseError(Exception):
    """文件能保存，但无法提取可索引文本。"""


def load_bytes(filename: str, data: bytes) -> list[Document]:
    """把数据库中的文件写入临时路径后再解析，来源名用原始文件名。"""
    suffix = Path(filename).suffix.lower()
    descriptor, name = tempfile.mkstemp(suffix=suffix or ".bin")
    os.close(descriptor)
    path = Path(name)
    try:
        path.write_bytes(data)
        documents = load_file(path)
    finally:
        path.unlink(missing_ok=True)
    for document in documents:
        document.metadata["source"] = filename
    return documents


def load_file(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _load_pdf(path)
    text = extract_text(path)
    if not text.strip():
        raise ParseError("未提取到文本")
    return [Document(page_content=text, metadata={"source": str(path)})]


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    loaders = {
        ".txt": _read_plain,
        ".md": _read_plain,
        ".markdown": _read_plain,
        ".docx": _read_docx,
        ".doc": _read_doc,
        ".xlsx": _read_excel,
        ".xls": _read_excel,
        ".csv": _read_csv,
        ".pptx": _read_pptx,
        ".html": _read_html,
        ".htm": _read_html,
        ".json": _read_json,
        ".ipynb": _read_ipynb,
    }
    loader = loaders.get(suffix)
    if loader is None:
        raise ParseError("不支持的文件格式")
    return loader(path).strip()


def _read_plain(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("无法识别文件编码")


def _load_pdf(path: Path) -> list[Document]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise ParseError("解析失败：文件已加密")
    except ParseError:
        raise
    except Exception as exc:
        message = str(exc).lower()
        if "encrypt" in message or "password" in message:
            raise ParseError("解析失败：文件已加密") from exc
        raise ParseError(f"解析失败：{exc}") from exc
    try:
        documents = PyPDFLoader(str(path)).load()
    except Exception as exc:
        message = str(exc).lower()
        if "encrypt" in message or "password" in message:
            raise ParseError("解析失败：文件已加密") from exc
        raise ParseError(f"解析失败：{exc}") from exc
    if not any(item.page_content.strip() for item in documents):
        raise ParseError("未提取到文本")
    return documents


def _read_docx(path: Path) -> str:
    document = DocxDocument(str(path))
    parts: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = paragraph.style.name if paragraph.style is not None else ""
        if style.startswith("Heading"):
            level_text = style.replace("Heading", "").strip() or "1"
            try:
                level = min(int(level_text), 6)
            except ValueError:
                level = 1
            parts.append(f"{'#' * level} {text}")
        elif "List" in style:
            parts.append(f"- {text}")
        else:
            parts.append(text)
    for table in document.tables:
        rendered = _rows_to_markdown(
            [[cell.text.strip().replace("\n", " ") for cell in row.cells] for row in table.rows]
        )
        if rendered:
            parts.append(rendered)
    return "\n\n".join(parts)


def _read_doc(path: Path) -> str:
    data = path.read_bytes()
    chunks: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(data) - 1:
        code = data[index] + (data[index + 1] << 8)
        if 32 <= code < 127 or code in (9, 10, 13) or 0x4E00 <= code <= 0x9FFF:
            current.append(chr(code))
            index += 2
            continue
        if len(current) >= 8:
            chunks.append("".join(current).strip())
        current = []
        index += 2
    if len(current) >= 8:
        chunks.append("".join(current).strip())
    text = "\n".join(item for item in chunks if item)
    if len(text) < 8:
        raise ParseError("旧版 .doc 未能提取正文，请另存为 .docx")
    return text


def _read_excel(path: Path) -> str:
    if path.suffix.lower() == ".xls":
        return _read_xls(path)
    workbook = load_workbook(path, data_only=True, read_only=True)
    parts: list[str] = []
    try:
        for sheet in workbook.worksheets:
            rows = [
                ["" if cell is None else str(cell) for cell in row]
                for row in sheet.iter_rows(values_only=True)
                if any(cell is not None and str(cell).strip() for cell in row)
            ]
            rendered = _rows_to_markdown(rows)
            if rendered:
                parts.append(f"## {sheet.title}\n\n{rendered}")
    finally:
        workbook.close()
    return "\n\n".join(parts)


def _read_xls(path: Path) -> str:
    import pandas as pd

    sheets = pd.read_excel(path, sheet_name=None)
    parts: list[str] = []
    for name, frame in sheets.items():
        rows = [list(frame.columns.astype(str))]
        rows.extend(frame.fillna("").astype(str).values.tolist())
        rendered = _rows_to_markdown(rows)
        if rendered:
            parts.append(f"## {name}\n\n{rendered}")
    return "\n\n".join(parts)


def _read_csv(path: Path) -> str:
    import pandas as pd

    last_error: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            frame = pd.read_csv(path, encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise ParseError("无法识别 CSV 编码") from last_error
    rows = [list(frame.columns.astype(str))]
    rows.extend(frame.fillna("").astype(str).values.tolist())
    return _rows_to_markdown(rows)


def _read_pptx(path: Path) -> str:
    presentation = Presentation(str(path))
    parts: list[str] = []
    for index, slide in enumerate(presentation.slides, start=1):
        lines = [f"## 幻灯片 {index}"]
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            text = shape.text_frame.text.strip()
            if text:
                lines.append(text)
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                if not notes.startswith("备注"):
                    notes = f"备注：{notes}"
                lines.append(notes)
        if len(lines) > 1:
            parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _read_html(path: Path) -> str:
    soup = BeautifulSoup(_read_plain(path), "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n")


def _read_json(path: Path) -> str:
    payload = json.loads(_read_plain(path))
    return "\n".join(_flatten_json(payload))


def _flatten_json(value, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            lines.extend(_flatten_json(item, child))
        return lines
    if isinstance(value, list):
        lines = []
        for index, item in enumerate(value):
            lines.extend(_flatten_json(item, f"{prefix}[{index}]"))
        return lines
    return [f"{prefix}: {value}"]


def _read_ipynb(path: Path) -> str:
    notebook = json.loads(_read_plain(path))
    parts: list[str] = []
    for index, cell in enumerate(notebook.get("cells", []), start=1):
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        source = source.strip()
        if not source:
            continue
        kind = cell.get("cell_type", "cell")
        parts.append(f"## 单元格 {index}（{kind}）\n{source}")
    return "\n\n".join(parts)


def _rows_to_markdown(rows: list[list[str]]) -> str:
    cleaned = [[str(cell).replace("|", "\\|").strip() for cell in row] for row in rows if any(str(cell).strip() for cell in row)]
    if not cleaned:
        return ""
    width = max(len(row) for row in cleaned)
    normalized = [row + [""] * (width - len(row)) for row in cleaned]
    header = normalized[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in normalized[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)
