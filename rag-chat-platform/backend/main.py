import os

# 必须在导入 HuggingFace / Chroma 之前设置，否则 Xet 大文件下载会停在 0 字节。
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from openai import APIStatusError, AsyncOpenAI, AuthenticationError
from starlette.requests import Request

from admin_router import router as admin_router
from auth import authenticate_token, ensure_admin, get_current_user
from auth_router import router as auth_router
from config import (
    ALLOWED_SUFFIXES,
    BLOCKED_SUFFIXES,
    COMING_SOON_FORMATS,
    DEEPSEEK_BASE_URL,
    DEFAULT_MODEL,
    FORMAT_BY_EXT,
    KNOWLEDGE_BASE_DIR,
    RETRIEVAL_TOP_K,
    SUPPORTED_FORMATS,
    format_limit_message,
)
from database import document_rows, init_db, read_document_bytes, save_document_bytes
from folders import create_folder, delete_folder, get_folder, list_folders, sync_from_disk
from history_router import router as history_router
from history_router import save_chat_history
from models import (
    ChatRequest,
    DepartmentListResponse,
    DocumentListResponse,
    IndexResponse,
    StatsResponse,
    UploadResponse,
    FolderCreateRequest,
)
from models_db import User
from parse_status import clear_status, get_status, set_status
from rag_engine import build_rag_prompt, index_knowledge_base, ingest_saved_file
from vector_store import collection_count, delete_folder_collection, department_count, search_departments
from router import route_query

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    sync_from_disk()
    ensure_admin()
    yield


app = FastAPI(title="RAG Knowledge Base Chat API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(history_router)


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or path in {"/api/health", "/api/auth/login"} or not path.startswith("/api"):
        return await call_next(request)
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return JSONResponse({"detail": "无效的登录凭证"}, status_code=401)
    try:
        authenticate_token(header.split(" ", 1)[1].strip())
    except HTTPException as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return await call_next(request)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _redact(text: str, secret: str) -> str:
    if secret and text:
        return text.replace(secret, "***")
    return text


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
    if suffix in BLOCKED_SUFFIXES:
        raise HTTPException(status_code=400, detail="不支持的文件格式")
    if suffix in {item["ext"] for item in COMING_SOON_FORMATS}:
        raise HTTPException(status_code=400, detail="该格式即将支持")
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="不支持的文件格式")
    return name


def _check_payload(data: bytes, suffix: str) -> None:
    if data.startswith(b"MZ"):
        raise HTTPException(status_code=400, detail="不支持的文件格式")
    if suffix == ".pdf" and not data.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="文件内容与扩展名不符")
    if suffix in {".docx", ".xlsx", ".pptx"} and not data.startswith(b"PK"):
        raise HTTPException(status_code=400, detail="文件内容与扩展名不符")
    limit = FORMAT_BY_EXT[suffix]["max_bytes"]
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=format_limit_message(suffix))


@app.get("/api/config")
async def runtime_config(_user: User = Depends(get_current_user)):
    seen: list[str] = []
    for item in COMING_SOON_FORMATS:
        if item["label"] not in seen and item["label"] != "JPEG":
            seen.append(item["label"])
    return {
        "formats": [
            {
                "ext": item["ext"],
                "label": item["label"],
                "max_mb": item["max_bytes"] // (1024 * 1024),
            }
            for item in SUPPORTED_FORMATS
        ],
        "coming_soon": seen,
        "accept": ",".join(item["ext"] for item in SUPPORTED_FORMATS),
    }


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/stats", response_model=StatsResponse)
async def stats(_user: User = Depends(get_current_user)):
    chunks = await asyncio.to_thread(collection_count)
    return StatsResponse(chunks=chunks)


def _department_files(dept: str) -> list[dict]:
    return document_rows(dept)


def _require_folder(folder_key: str) -> str:
    if get_folder(folder_key) is None:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    return folder_key


@app.get("/api/documents", response_model=DocumentListResponse)
async def list_documents(_user: User = Depends(get_current_user)):
    sync_from_disk()
    return DocumentListResponse(files=document_rows())


@app.get("/api/departments", response_model=DepartmentListResponse)
async def list_departments(_user: User = Depends(get_current_user)):
    sync_from_disk()
    departments = []
    for folder in list_folders():
        departments.append(
            {
                "key": folder["key"],
                "name": folder["name"],
                "description": folder["description"],
                "chunk_count": await asyncio.to_thread(department_count, folder["key"]),
                "files": _department_files(folder["key"]),
            }
        )
    return DepartmentListResponse(departments=departments)


@app.post("/api/folders")
async def create_folder_endpoint(payload: FolderCreateRequest, _user: User = Depends(get_current_user)):
    try:
        return create_folder(payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/folders/{folder_key}")
async def delete_folder_endpoint(folder_key: str, _user: User = Depends(get_current_user)):
    if get_folder(folder_key) is None:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    await asyncio.to_thread(delete_folder_collection, folder_key)
    try:
        delete_folder(folder_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok", "key": folder_key}


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest, current_user: User = Depends(get_current_user)):
    """RAG 问答接口：检索 → 增强 → 流式生成。"""
    api_key = request.config.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=401, detail="缺少 API Key")
    user_id = current_user.id

    target_departments, via = await route_query(
        query=request.message,
        api_key=api_key,
        base_url=request.config.base_url,
        model=request.config.model_name,
    )
    router_payload = {
        "type": "router",
        "via": via,
        "departments": [
            {"key": dept, "name": (get_folder(dept) or {}).get("name", dept)} for dept in target_departments
        ],
    }

    try:
        hits = await asyncio.to_thread(
            search_departments, target_departments, request.message, RETRIEVAL_TOP_K
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"知识库检索失败: {_safe_error(exc, api_key)}")

    labeled_docs = [f"[来源: {hit['source']}]\n{hit['content']}" for hit in hits]
    system_prompt = build_rag_prompt(request.message, labeled_docs)
    sources = [
        {
            "index": index,
            "source": hit["source"],
            "department": hit["department"],
            "department_name": hit["department_name"],
            "preview": " ".join(hit["content"].split())[:80],
            "excerpt": hit["content"],
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
        parts: list[str] = []
        error_message: str | None = None
        finished = False
        try:
            yield _sse(router_payload)
            if sources:
                yield _sse({"type": "sources", "sources": sources})
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    parts.append(content)
                    yield _sse({"type": "delta", "content": content})
            yield _sse({"type": "done"})
            finished = True
        except AuthenticationError:
            error_message = "API Key 无效或未授权"
            yield _sse({"type": "error", "message": error_message})
        except Exception as exc:
            error_message = _safe_error(exc, api_key)
            yield _sse({"type": "error", "message": error_message})
        finally:
            content = "".join(parts)
            if error_message:
                content = f"{content}\n\n{error_message}" if content else error_message
            elif not content:
                content = "没有收到模型输出" if finished else "已停止生成"
            citations = [
                {
                    "file": str(hit.get("source") or "未知来源"),
                    "snippet": str(hit.get("content") or "")[:800],
                }
                for hit in hits
                if hit.get("content")
            ]
            try:
                save_chat_history(
                    user_id,
                    _redact(request.message, api_key),
                    _redact(content, api_key),
                    citations,
                    [item["name"] for item in router_payload["departments"]],
                )
            except Exception:
                pass

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
async def index_endpoint(department: str | None = Query(default=None), _user: User = Depends(get_current_user)):
    """触发知识库重新索引。可只重建一个部门。"""
    if department is not None:
        _require_folder(department)
    try:
        result = await asyncio.to_thread(index_knowledge_base, department)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"索引失败: {exc}")
    return IndexResponse(**result)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    department: str = Form(...),
    file: UploadFile = File(...),
    _user: User = Depends(get_current_user),
):
    """上传文档到指定部门目录，并在后台解析、索引。"""
    _require_folder(department)
    filename = _safe_filename(file.filename)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    _check_payload(data, Path(filename).suffix.lower())

    save_document_bytes(
        department,
        filename,
        data,
        status="parsing",
        content_hash=hashlib.sha256(data).hexdigest(),
    )
    _remove_disk_copy(department, filename)
    background_tasks.add_task(ingest_saved_file, department, filename)
    return UploadResponse(status="parsing", filename=filename, department=department)


@app.post("/api/documents/{department}/{filename}/retry")
async def retry_document(
    department: str,
    filename: str,
    background_tasks: BackgroundTasks,
    _user: User = Depends(get_current_user),
):
    """重新解析并索引一个失败的文件。"""
    _require_folder(department)
    safe_name = _safe_filename(filename)
    if read_document_bytes(department, safe_name) is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    set_status(department, safe_name, "parsing")
    background_tasks.add_task(ingest_saved_file, department, safe_name)
    return {"status": "parsing", "filename": safe_name, "department": department}


@app.delete("/api/documents/{department}/{filename}")
async def delete_document(department: str, filename: str, _user: User = Depends(get_current_user)):
    """删除某个部门下的文档。删除后需要重建该部门索引。"""
    _require_folder(department)
    safe_name = _safe_filename(filename)
    if get_status(department, safe_name) is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    clear_status(department, safe_name)
    _remove_disk_copy(department, safe_name)
    return {"status": "ok", "filename": safe_name, "department": department}


def _remove_disk_copy(department: str, filename: str) -> None:
    target = Path(KNOWLEDGE_BASE_DIR) / department / filename
    if target.is_file():
        target.unlink()
