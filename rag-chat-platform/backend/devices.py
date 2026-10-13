from functools import lru_cache

from config import MODEL_DEVICE


@lru_cache(maxsize=1)
def model_device() -> str:
    """本地模型运行设备。auto 时有可用 CUDA 就用 GPU。"""
    if MODEL_DEVICE and MODEL_DEVICE != "auto":
        return MODEL_DEVICE
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def device_info() -> dict:
    device = model_device()
    info = {"device": device}
    if device.startswith("cuda"):
        try:
            import torch

            info["gpu"] = torch.cuda.get_device_name(0)
            info["memory_allocated_mb"] = round(torch.cuda.memory_allocated(0) / 1024 / 1024)
        except Exception:
            pass
    return info
