from __future__ import annotations

import logging
import threading

from config import RERANK_MIN_SCORE, RERANKER_ENABLED, RERANKER_MODEL
from devices import empty_cuda_cache, reranker_device
from safe_strings import safe_exception_message

_log = logging.getLogger("rag.embed")

_load_lock = threading.Lock()
_predict_lock = threading.Lock()
_model = None
_load_failed = False
_loaded_device: str | None = None


def reranker_enabled() -> bool:
    """auto：只要本机能跑就启用（GPU 或 CPU）；0 关闭。"""
    if RERANKER_ENABLED == "auto":
        return True
    return RERANKER_ENABLED in {"1", "true", "yes", "on"}


def reranker_status() -> str:
    if not reranker_enabled():
        return "disabled"
    if _model is not None:
        return f"ready:{_loaded_device or '?'}"
    return "failed" if _load_failed else "loading"


def _load_on(device: str):
    import torch
    from sentence_transformers import CrossEncoder

    from model_download import ensure_local_model

    empty_cuda_cache()
    kwargs = {}
    if device.startswith("cuda"):
        kwargs["model_kwargs"] = {"torch_dtype": torch.float16}
    model = CrossEncoder(
        ensure_local_model(RERANKER_MODEL),
        device=device,
        max_length=512,
        **kwargs,
    )
    if device.startswith("cuda"):
        model.half()
        empty_cuda_cache()
    return model


def get_reranker():
    """加载交叉编码重排模型。GPU OOM 时自动改到 CPU，不再永久放弃。"""
    global _model, _load_failed, _loaded_device
    if _model is not None or _load_failed or not reranker_enabled():
        return _model
    with _load_lock:
        if _model is not None or _load_failed:
            return _model
        preferred = reranker_device()
        candidates = [preferred]
        if preferred.startswith("cuda"):
            candidates.append("cpu")
        last_error: Exception | None = None
        for device in candidates:
            try:
                model = _load_on(device)
                _model = model
                _loaded_device = device
                _log.info("已加载 %s (%s)", RERANKER_MODEL, device)
                return _model
            except Exception as exc:
                last_error = exc
                empty_cuda_cache()
                _log.warning("重排模型在 %s 加载失败: %s", device, safe_exception_message(exc))
        _load_failed = True
        _log.warning(
            "重排模型不可用,改用融合排序: %s",
            safe_exception_message(last_error) if last_error else "未知",
        )
    return _model


def rerank(query: str, hits: list[dict], top_n: int) -> list[dict] | None:
    """按与 query 的相关度重排。重排不可用时返回 None。"""
    model = get_reranker()
    if model is None or not hits:
        return None
    # CPU 上大批量会很慢；GPU 上也控制显存峰值
    batch_size = 4 if (_loaded_device or "").startswith("cpu") else 8
    with _predict_lock:
        scores = model.predict(
            [(query, hit["content"]) for hit in hits],
            batch_size=batch_size,
            show_progress_bar=False,
        )
    for hit, score in zip(hits, scores):
        hit["rerank_score"] = float(score)
    ranked = sorted(hits, key=lambda hit: hit["rerank_score"], reverse=True)
    kept = [hit for hit in ranked if hit["rerank_score"] >= RERANK_MIN_SCORE]
    return (kept or ranked[:1])[:top_n]
