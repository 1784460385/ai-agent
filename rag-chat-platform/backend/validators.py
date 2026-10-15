"""文件元数据与内容校验。

集中处理:
- 文件名清理(Path traversal / 危险后缀 / 隐藏文件)
- 文件 magic bytes 与扩展名一致性
- 大小限制

设计原则:
- 校验失败一律抛 HTTPException,FastAPI 自动包装 4xx 响应
- 函数独立、无副作用,便于单元测试
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from config import (
    ALLOWED_SUFFIXES,
    BLOCKED_SUFFIXES,
    COMING_SOON_FORMATS,
    FORMAT_BY_EXT,
    format_limit_message,
)

# 文件 magic bytes 校验表
_IMAGE_MAGIC: dict[str, tuple[bytes, ...]] = {
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".webp": (b"RIFF",),  # 二次校验 data[8:12] == b"WEBP"
    ".bmp": (b"BM",),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
}


def safe_filename(filename: str | None) -> str:
    """清理并校验文件名。返回 basename。

    拒绝:
    - 缺失文件名
    - 仅 . 或 ..
    - 隐藏文件(.开头)
    - 黑名单后缀(.exe/.bat/.sh/...)
    - coming-soon 格式
    - 未声明的后缀
    """
    if not filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    name = Path(filename).name
    if not name or name in {".", ".."} or name.startswith("."):
        raise HTTPException(status_code=400, detail="无效文件名")
    suffix = Path(name).suffix.lower()
    if suffix in BLOCKED_SUFFIXES:
        raise HTTPException(status_code=400, detail="不支持的文件格式")
    if suffix in {item["ext"] for item in COMING_SOON_FORMATS}:
        raise HTTPException(status_code=400, detail="该格式即将支持")
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="不支持的文件格式")
    return name


def check_payload(data: bytes, suffix: str) -> None:
    """校验文件内容与扩展名一致,并按格式限制大小。

    校验类型:
    - .pdf 必须以 %PDF 开头
    - .docx/.xlsx/.pptx (ZIP) 必须以 PK 开头
    - 图片必须有正确 magic bytes(webp 还要 WEBP 二次校验)
    - 大小超过 FORMAT_BY_EXT[suffix]["max_bytes"] → 413
    """
    if data.startswith(b"MZ"):
        raise HTTPException(status_code=400, detail="不支持的文件格式")
    if suffix == ".pdf" and not data.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="文件内容与扩展名不符")
    if suffix in {".docx", ".xlsx", ".pptx"} and not data.startswith(b"PK"):
        raise HTTPException(status_code=400, detail="文件内容与扩展名不符")
    if suffix in _IMAGE_MAGIC:
        if not any(data.startswith(magic) for magic in _IMAGE_MAGIC[suffix]):
            raise HTTPException(status_code=400, detail="文件内容与扩展名不符")
        if suffix == ".webp" and data[8:12] != b"WEBP":
            raise HTTPException(status_code=400, detail="文件内容与扩展名不符")
    limit = FORMAT_BY_EXT[suffix]["max_bytes"]
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=format_limit_message(suffix))