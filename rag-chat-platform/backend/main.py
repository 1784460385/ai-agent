import os

# 必须在导入 HuggingFace / Chroma 之前设置，否则 Xet 大文件下载会停在 0 字节。
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import APIStatusError, AsyncOpenAI, AuthenticationError

from config import (
    ALLOWED_SUFFIXES,
    DEEPSEEK_BASE_URL,
    DEFAULT_MODEL,
    KNOWLEDGE_BASE_DIR,
    MAX_UPLOAD_BYTES,
    RETRIEVAL_TOP_K,
)
from models import (
    ChatRequest,
    DocumentListResponse,
    IndexResponse,
    StatsResponse,
    UploadResponse,
)
from rag_engine import build_rag_prompt, index_knowledge_base
from vector_store import collection_count, search

app = FastAPI(title="RAG Knowledge Base Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _safe_error(exc: Exception, api_key: str) -> str:
    text = str(exc)
    if api_key:
        text = text.replace(api_key, "***")
    return text[:500]


def _safe_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    name = Path(filename).name
    if not name or name in {".", ".."} or name.startswith("."):
        raise HTTPException(status_code=400, detail="无效文件名")
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="仅支持 PDF、Markdown、TXT")
    return name


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/stats", response_model=StatsResponse)
async def stats():
    chunks = await asyncio.to_thread(collection_count)
    return StatsResponse(chunks=chunks)


@app.get("/api/documents", response_model=DocumentListResponse)
async def list_documents():
    os.makedirs(KNOWLEDGE_BASE_DIR, exist_ok=True)
    files = []
    root = Path(KNOWLEDGE_BASE_DIR)
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        files.append({"name": path.name, "size": path.stat().st_size})
    return DocumentListResponse(files=files)


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """RAG 问答接口：检索 → 增强 → 流式生成。"""
    api_key = request.config.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=401, detail="缺少 API Key")

    try:
        hits = await asyncio.to_thread(search, request.message, RETRIEVAL_TOP_K)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"知识库检索失败: {_safe_error(exc, api_key)}")

    labeled_docs = [f"[来源: {hit['source']}]\n{hit['content']}" for hit in hits]
    system_prompt = build_rag_prompt(request.message, labeled_docs)
    sources = [
        {
            "index": index,
            "source": hit["source"],
            "preview": " ".join(hit["content"].split())[:80],
        }
        for index, hit in enumerate(hits, start=1)
    ]

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=request.config.base_url or DEEPSEEK_BASE_URL,
        max_retries=0,
        timeout=90,
    )

    try:
        stream = await client.chat.completions.create(
            model=request.config.model_name or DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.message},
            ],
            stream=True,
            temperature=0.3,
        )
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="API Key 无效或未授权")
    except APIStatusError as exc:
        if exc.status_code == 401:
            raise HTTPException(status_code=401, detail="API Key 无效或未授权")
        raise HTTPException(
            status_code=502,
            detail=f"模型服务返回错误 ({exc.status_code})",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"模型服务不可用: {_safe_error(exc, api_key)}")

    async def event_stream():
        if sources:
            yield _sse({"type": "sources", "sources": sources})
        try:
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield _sse({"type": "delta", "content": content})
            yield _sse({"type": "done"})
        except AuthenticationError:
            yield _sse({"type": "error", "message": "API Key 无效或未授权"})
        except Exception as exc:
            yield _sse({"type": "error", "message": _safe_error(exc, api_key)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/index", response_model=IndexResponse)
async def index_endpoint():
    """触发知识库重新索引。"""
    try:
        result = await asyncio.to_thread(index_knowledge_base)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"索引失败: {exc}")
    return IndexResponse(**result)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """上传文档到知识库目录。"""
    filename = _safe_filename(file.filename)
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 20MB")
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")

    os.makedirs(KNOWLEDGE_BASE_DIR, exist_ok=True)
    target = Path(KNOWLEDGE_BASE_DIR) / filename
    target.write_bytes(data)
    return UploadResponse(status="ok", filename=filename)
