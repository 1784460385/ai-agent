"""图片 OCR：基于 RapidOCR（默认中英文），供知识库摄入使用。"""

from __future__ import annotations

import io
import threading
from typing import Any

import numpy as np
from PIL import Image

from config import OCR_ENABLED, OCR_MAX_IMAGE_PIXELS

_lock = threading.Lock()
_engine = None


class OcrError(Exception):
    """OCR 失败。"""


def ocr_available() -> bool:
    return bool(OCR_ENABLED)


def get_ocr_engine():
    global _engine
    if not OCR_ENABLED:
        raise OcrError("OCR 已禁用（OCR_ENABLED=0）")
    if _engine is not None:
        return _engine
    with _lock:
        if _engine is None:
            from rapidocr import RapidOCR

            _engine = RapidOCR()
            print("[OCR] RapidOCR 已加载", flush=True)
    return _engine


def _load_image(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
    except Exception as exc:
        raise OcrError(f"无法打开图片：{exc}") from exc
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    elif image.mode == "L":
        image = image.convert("RGB")
    width, height = image.size
    if width * height > OCR_MAX_IMAGE_PIXELS:
        scale = (OCR_MAX_IMAGE_PIXELS / (width * height)) ** 0.5
        image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))))
    return image


def _lines_from_result(result: Any) -> list[str]:
    txts = getattr(result, "txts", None) or ()
    boxes = getattr(result, "boxes", None)
    if not txts:
        return []
    items: list[tuple[float, float, str]] = []
    for index, text in enumerate(txts):
        content = str(text).strip()
        if not content:
            continue
        y = float(index)
        x = 0.0
        if boxes is not None and index < len(boxes):
            box = np.asarray(boxes[index], dtype=float)
            if box.ndim == 2 and box.shape[0] >= 2:
                y = float(box[:, 1].mean())
                x = float(box[:, 0].mean())
        items.append((y, x, content))
    items.sort(key=lambda item: (round(item[0] / 12), item[1]))
    return [item[2] for item in items]


def ocr_image_bytes(data: bytes) -> str:
    """对图片字节做 OCR，返回按阅读顺序排列的纯文本。"""
    if not data:
        raise OcrError("图片为空")
    image = _load_image(data)
    array = np.asarray(image)
    try:
        result = get_ocr_engine()(array)
    except OcrError:
        raise
    except Exception as exc:
        raise OcrError(f"OCR 识别失败：{exc}") from exc
    lines = _lines_from_result(result)
    return "\n".join(lines).strip()


def ocr_image_path(path: str) -> str:
    return ocr_image_bytes(open(path, "rb").read())
