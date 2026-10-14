from functools import lru_cache

from config import MODEL_DEVICE, RERANKER_DEVICE


@lru_cache(maxsize=1)
def model_device() -> str:
    """Embedding 模型运行设备。auto 时有可用 CUDA 就用 GPU。"""
    if MODEL_DEVICE and MODEL_DEVICE != "auto":
        return MODEL_DEVICE
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def gpu_total_gb() -> float | None:
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        return torch.cuda.get_device_properties(0).total_memory / (1024**3)
    except Exception:
        return None


def reranker_device() -> str:
    """重排模型设备。4GB 级显卡上 embedding 已占满 GPU，默认把重排放到 CPU。"""
    if RERANKER_DEVICE and RERANKER_DEVICE != "auto":
        return RERANKER_DEVICE
    embed = model_device()
    if not embed.startswith("cuda"):
        return "cpu"
    total = gpu_total_gb()
    # 3050 Laptop 4GB：bge-m3 + bge-reranker-v2-m3 放不下，重排改 CPU
    if total is not None and total < 6.0:
        return "cpu"
    return "cuda"


def empty_cuda_cache() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def device_info() -> dict:
    device = model_device()
    info = {
        "device": device,
        "reranker_device": reranker_device(),
    }
    if device.startswith("cuda") or reranker_device().startswith("cuda"):
        try:
            import torch

            info["gpu"] = torch.cuda.get_device_name(0)
            info["gpu_total_gb"] = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2)
            info["memory_allocated_mb"] = round(torch.cuda.memory_allocated(0) / 1024 / 1024)
        except Exception:
            pass
    return info
