import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from config import BASE_DIR

HUB_ID = re.compile(r"^[\w.-]+/[\w.-]+$")
SKIP_PREFIXES = ("imgs/", "onnx/", ".")
SKIP_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".ds_store"}
COMPLETE_MARKER = ".download_complete"
# 官方 BAAI/bge-m3 的关键文件。本地尺寸一致时不再访问网络。
REQUIRED_FILES = {
    "BAAI/bge-m3": {
        "config.json": 687,
        "modules.json": 349,
        "config_sentence_transformers.json": 123,
        "sentence_bert_config.json": 54,
        "1_Pooling/config.json": 191,
        "tokenizer_config.json": 444,
        "special_tokens_map.json": 964,
        "tokenizer.json": 17098108,
        "sentencepiece.bpe.model": 5069051,
        "pytorch_model.bin": 2271145830,
    },
}


def _endpoint() -> str:
    return os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")


def _hub_files(model_id: str) -> list[str]:
    request = urllib.request.Request(
        f"{_endpoint()}/api/models/{model_id}",
        headers={"User-Agent": "rag-chat-platform"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    names: list[str] = []
    for item in payload.get("siblings") or []:
        name = item.get("rfilename") or ""
        if not name or name.startswith(SKIP_PREFIXES):
            continue
        if Path(name).suffix.lower() in SKIP_SUFFIXES:
            continue
        names.append(name)
    if not names:
        raise RuntimeError(f"没有从模型仓库读到文件列表: {model_id}")
    return names


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    downloaded = part.stat().st_size if part.exists() else 0

    for attempt in range(3):
        headers = {"User-Agent": "rag-chat-platform"}
        if downloaded:
            headers["Range"] = f"bytes={downloaded}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                if downloaded and response.status != 206:
                    downloaded = 0
                mode = "ab" if downloaded and response.status == 206 else "wb"
                remaining = int(response.headers.get("Content-Length") or 0)
                total = downloaded + remaining if mode == "ab" else remaining
                next_report = downloaded
                with part.open(mode) as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        downloaded += len(chunk)
                        if downloaded - next_report >= 8 * 1024 * 1024 or (total and downloaded >= total):
                            if total:
                                print(
                                    f"[model] {dest.name} {downloaded / 1024 / 1024:.0f}/{total / 1024 / 1024:.0f} MB",
                                    flush=True,
                                )
                            else:
                                print(f"[model] {dest.name} {downloaded / 1024 / 1024:.0f} MB", flush=True)
                            next_report = downloaded
            break
        except (TimeoutError, urllib.error.URLError) as exc:
            if attempt == 2:
                raise RuntimeError(f"下载失败: {dest.name}") from exc
            print(f"[model] {dest.name} 下载中断，正在重试 ({attempt + 1}/3)", flush=True)

    part.replace(dest)


def _local_ready(dest: Path, model_id: str) -> bool:
    if not dest.is_dir():
        return False
    if (dest / COMPLETE_MARKER).is_file():
        return True
    required = REQUIRED_FILES.get(model_id)
    if not required:
        return False
    for name, size in required.items():
        path = dest / name
        if not path.is_file() or path.stat().st_size != size:
            return False
    return True


def ensure_local_model(model_id: str) -> str:
    """把 Hub 模型下到本地目录。已是本地路径或已下完整时直接返回。"""
    candidate = Path(model_id)
    if candidate.exists():
        return str(candidate)
    if not HUB_ID.match(model_id):
        return model_id

    dest = BASE_DIR / "models" / model_id
    if _local_ready(dest, model_id):
        print(f"[model] 使用本地模型 {dest}", flush=True)
        return str(dest)

    print(f"[model] 准备模型 {model_id} -> {dest}", flush=True)
    for name in _hub_files(model_id):
        target = dest / name
        if target.exists() and target.stat().st_size > 0:
            continue
        _download(f"{_endpoint()}/{model_id}/resolve/main/{name}", target)
    (dest / COMPLETE_MARKER).write_text("ok", encoding="utf-8")
    return str(dest)
