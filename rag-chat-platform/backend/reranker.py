from __future__ import annotations

import threading

from config import RERANK_MIN_SCORE, RERANKER_ENABLED, RERANKER_MODEL
from devices import model_device

_load_lock = threading.Lock()
_predict_lock = threading.Lock()
_model = None
_load_failed = False


def reranker_enabled() -> bool:
    if RERANKER_ENABLED == "auto":
        return model_device().startswith("cuda")
    return RERANKER_ENABLED in {"1", "true", "yes", "on"}


def reranker_status() -> str:
    if not reranker_enabled():
        return "disabled"
    if _model is not None:
        return "ready"
    return "failed" if _load_failed else "loading"


def get_reranker():
    """加载交叉编码重排模型。加载失败只记一次日志，之后检索退回融合排序。"""
    global _model, _load_failed
    if _model is not None or _load_failed or not reranker_enabled():
        return _model
    with _load_lock:
        if _model is None and not _load_failed:
            try:
                from sentence_transformers import CrossEncoder

                from model_download import ensure_local_model

                device = model_device()
                model = CrossEncoder(ensure_local_model(RERANKER_MODEL), device=device, max_length=512)
                if device.startswith("cuda"):
                    model.half()
                _model = model
                print(f"[RERANK] 已加载 {RERANKER_MODEL} ({device})", flush=True)
            except Exception as exc:
                _load_failed = True
                print(f"[WARN] 重排模型加载失败，改用融合排序: {exc}", flush=True)
    return _model


def rerank(query: str, hits: list[dict], top_n: int) -> list[dict] | None:
    """按与 query 的相关度重排。重排不可用时返回 None。"""
    model = get_reranker()
    if model is None or not hits:
        return None
    with _predict_lock:
        scores = model.predict(
            [(query, hit["content"]) for hit in hits],
            batch_size=16,
            show_progress_bar=False,
        )
    for hit, score in zip(hits, scores):
        hit["rerank_score"] = float(score)
    ranked = sorted(hits, key=lambda hit: hit["rerank_score"], reverse=True)
    kept = [hit for hit in ranked if hit["rerank_score"] >= RERANK_MIN_SCORE]
    return (kept or ranked[:1])[:top_n]
