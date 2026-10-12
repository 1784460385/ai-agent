import base64
from pathlib import Path

from config import BLOCKED_SUFFIXES, FORMAT_BY_EXT
from file_parsers import ParseError, load_bytes

MAX_ATTACHMENTS = 3
IMAGE_MAX_BYTES = 10 * 1024 * 1024
TEXT_CHARS = 8000
SUMMARY_CHARS = 500
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
VISION_MODELS = {"deepseek-flash", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"}
_IMAGE_MAGIC = {
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webp": (b"RIFF",),
}


class AttachmentError(Exception):
    pass


def vision_model(model_name: str) -> bool:
    return (model_name or "").strip() in VISION_MODELS


def prepare_attachments(files: list[tuple[str, bytes]]) -> dict:
    if len(files) > MAX_ATTACHMENTS:
        raise AttachmentError(f"一次最多上传 {MAX_ATTACHMENTS} 个附件")
    records = []
    images = []
    blocks = []
    for filename, data in files:
        name = Path(filename).name
        suffix = Path(name).suffix.lower()
        if not name or name.startswith(".") or suffix in BLOCKED_SUFFIXES:
            raise AttachmentError(f"不支持的文件：{name or '未命名'}")
        if suffix in IMAGE_SUFFIXES:
            record, image = _prepare_image(name, suffix, data)
            records.append(record)
            images.append(image)
            continue
        if suffix not in FORMAT_BY_EXT:
            raise AttachmentError(f"不支持的文件格式：{name}")
        limit = FORMAT_BY_EXT[suffix]["max_bytes"]
        if len(data) > limit:
            raise AttachmentError(f"{name} 超过 {limit // (1024 * 1024)}MB")
        text = _read_document(name, data)
        records.append({"name": name, "kind": "file", "summary": text[:SUMMARY_CHARS]})
        blocks.append(f"[{name}]\n{text}")
    return {"records": records, "images": images, "document_text": "\n\n".join(blocks)}


def compose_user_text(question: str, document_text: str) -> str:
    parts = []
    if question.strip():
        parts.append(question.strip())
    if document_text.strip():
        parts.append("用户附带的资料\n" + document_text.strip())
    return "\n\n".join(parts) or "请根据附件回答"


def _prepare_image(name: str, suffix: str, data: bytes) -> tuple[dict, dict]:
    if len(data) > IMAGE_MAX_BYTES:
        raise AttachmentError(f"{name} 超过 10MB")
    magic = _IMAGE_MAGIC[suffix]
    if not any(data.startswith(item) for item in magic):
        raise AttachmentError(f"{name} 的内容与扩展名不符")
    if suffix == ".webp" and (len(data) < 12 or data[8:12] != b"WEBP"):
        raise AttachmentError(f"{name} 的内容与扩展名不符")
    encoded = base64.b64encode(data).decode("ascii")
    return (
        {"name": name, "kind": "image", "summary": "图片已随问题发送"},
        {"mime": IMAGE_MIME[suffix], "data_url": f"data:{IMAGE_MIME[suffix]};base64,{encoded}"},
    )


def _read_document(name: str, data: bytes) -> str:
    try:
        documents = load_bytes(name, data)
    except ParseError as exc:
        raise AttachmentError(f"{name}：{exc}") from exc
    except Exception as exc:
        raise AttachmentError(f"{name} 解析失败") from exc
    text = "\n".join(item.page_content.strip() for item in documents if item.page_content.strip())
    if not text:
        raise AttachmentError(f"{name} 未提取到文本")
    if len(text) > TEXT_CHARS:
        return text[:TEXT_CHARS] + "\n……（下文已截断）"
    return text
