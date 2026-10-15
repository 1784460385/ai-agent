from config import apply_env  # noqa: F401  必须在所有 huggingface/chroma 模块之前

apply_env()  # 一次性触发模块顶部声明的默认值,确保后续 import 安全

import asyncio
import hashlib
import json
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.requests import Request

from admin_router import router as admin_router
from auth import ensure_admin, get_current_user
from auth_router import router as auth_router
from chat_router import router as chat_router
from config import (
    COMING_SOON_FORMATS,
    IMAGE_MAX_BYTES,
    KNOWLEDGE_BASE_DIR,
    OCR_ENABLED,
    OCR_TIMEOUT_SECONDS,
    SUPPORTED_FORMATS,
)
from database import (
    document_rows,
    init_db,
    isolate_folders,
    read_document_bytes,
    read_normalized_markdown,
    save_document_bytes,
)
from devices import device_info
from file_parsers import ParseError, load_bytes
from folders import create_folder, delete_folder, get_folder, list_folders, rename_folder, sync_from_disk
from history_router import backfill_conversations
from history_router import router as history_router
from history_router import threads as thread_router
from keys_router import router as keys_router
from logging_config import configure_logging, get_logger
from models import (
    DepartmentListResponse,
    DocumentListResponse,
    DocumentMoveRequest,
    DocumentPreviewResponse,
    IndexResponse,
    StatsResponse,
    UploadResponse,
    FolderCreateRequest,
    FolderRenameRequest,
)
from models_db import User
from parse_status import clear_status, get_status, set_status
from rag_engine import ingest_saved_file, index_knowledge_base
from rate_limit import install_rate_limiter
from reranker import reranker_status
from safe_strings import public_error
from validators import check_payload, safe_filename
from vector_store import (
    collection_count,
    delete_folder_collection,
    department_count,
    warmup_models,
)

configure_logging()
log = get_logger("rag.main")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    admin_id = ensure_admin()
    isolate_folders(admin_id)
    sync_from_disk(admin_id)
    backfill_conversations()
    threading.Thread(target=warmup_models, name="model-warmup", daemon=True).start()
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

# 限速:关键接口(chat/login/upload/index)按用户 token 或 IP 做 token bucket
install_rate_limiter(app)


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(history_router)
app.include_router(thread_router)
app.include_router(keys_router)
app.include_router(chat_router)


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or path in {"/api/health", "/api/auth/login"} or not path.startswith("/api"):
        return await call_next(request)
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return JSONResponse({"detail": public_error("auth_invalid_credentials")}, status_code=401)
    try:
        from auth import authenticate_token

        authenticate_token(header.split(" ", 1)[1].strip())
    except HTTPException as exc:
        return JSONResponse({"detail": public_error("auth_invalid_credentials")}, status_code=exc.status_code)
    return await call_next(request)


# ---- 系统 ----
@app.get("/api/config")
async def runtime_config(_user: User = Depends(get_current_user)):
    seen: list[str] = []
    for item in COMING_SOON_FORMATS:
        if item["label"] not in seen:
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
        "ocr_enabled": OCR_ENABLED,
        "image_max_mb": IMAGE_MAX_BYTES // (1024 * 1024),
        "ocr_timeout_seconds": OCR_TIMEOUT_SECONDS,
    }


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        **device_info(),
        "reranker": reranker_status(),
    }


@app.get("/api/stats", response_model=StatsResponse)
async def stats(current_user: User = Depends(get_current_user)):
    chunks = await asyncio.to_thread(collection_count, current_user.id)
    return StatsResponse(chunks=chunks)


# ---- 文件夹 ----
def _department_files(user_id: int, dept: str) -> list[dict]:
    return document_rows(user_id, dept)


def _require_folder(user_id: int, folder_key: str) -> str:
    if get_folder(user_id, folder_key) is None:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    return folder_key


@app.get("/api/documents", response_model=DocumentListResponse)
async def list_documents(current_user: User = Depends(get_current_user)):
    return DocumentListResponse(files=document_rows(current_user.id))


@app.get("/api/departments", response_model=DepartmentListResponse)
async def list_departments(current_user: User = Depends(get_current_user)):
    departments = []
    for folder in list_folders(current_user.id):
        departments.append(
            {
                "key": folder["key"],
                "name": folder["name"],
                "description": folder["description"],
                "chunk_count": await asyncio.to_thread(department_count, current_user.id, folder["key"]),
                "files": _department_files(current_user.id, folder["key"]),
            }
        )
    return DepartmentListResponse(departments=departments)


@app.post("/api/folders")
async def create_folder_endpoint(payload: FolderCreateRequest, current_user: User = Depends(get_current_user)):
    try:
        return create_folder(current_user.id, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/folders/{folder_key}")
async def rename_folder_endpoint(
    folder_key: str,
    payload: FolderRenameRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        return rename_folder(current_user.id, folder_key, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/folders/{folder_key}")
async def delete_folder_endpoint(folder_key: str, current_user: User = Depends(get_current_user)):
    if get_folder(current_user.id, folder_key) is None:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    await asyncio.to_thread(delete_folder_collection, current_user.id, folder_key)
    try:
        delete_folder(current_user.id, folder_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok", "key": folder_key}


# ---- 文档 ----
@app.post("/api/index", response_model=IndexResponse)
async def index_endpoint(department: str | None = Query(default=None), current_user: User = Depends(get_current_user)):
    """触发知识库重新索引。可只重建一个部门。"""
    if department is not None:
        _require_folder(current_user.id, department)
    try:
        result = await asyncio.to_thread(index_knowledge_base, current_user.id, department)
    except Exception as exc:
        # 安全:对外只给固定文案,详细堆栈进日志
        log.exception("索引失败 user=%s department=%s", current_user.id, department)
        raise HTTPException(status_code=500, detail=public_error("internal_error")) from exc
    return IndexResponse(**result)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    department: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """上传文档到当前用户的文件夹,并在后台解析、索引。"""
    _require_folder(current_user.id, department)
    filename = safe_filename(file.filename)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    check_payload(data, Path(filename).suffix.lower())

    save_document_bytes(
        current_user.id,
        department,
        filename,
        data,
        status="parsing",
        content_hash=hashlib.sha256(data).hexdigest(),
    )
    _remove_disk_copy(department, filename)
    background_tasks.add_task(ingest_saved_file, current_user.id, department, filename)
    return UploadResponse(status="parsing", filename=filename, department=department)


@app.post("/api/documents/{department}/{filename}/retry")
async def retry_document(
    department: str,
    filename: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """重新解析并索引一个失败的文件。"""
    _require_folder(current_user.id, department)
    safe_name = safe_filename(filename)
    if read_document_bytes(current_user.id, department, safe_name) is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    set_status(current_user.id, department, safe_name, "parsing")
    background_tasks.add_task(ingest_saved_file, current_user.id, department, safe_name)
    return {"status": "parsing", "filename": safe_name, "department": department}


@app.delete("/api/documents/{department}/{filename}")
async def delete_document(department: str, filename: str, current_user: User = Depends(get_current_user)):
    """删除当前用户某个文件夹下的文档。删除后需要重建该文件夹索引。"""
    _require_folder(current_user.id, department)
    safe_name = safe_filename(filename)
    if get_status(current_user.id, department, safe_name) is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    clear_status(current_user.id, department, safe_name)
    _remove_disk_copy(department, safe_name)
    return {"status": "ok", "filename": safe_name, "department": department}


@app.get("/api/documents/{department}/{filename}/preview", response_model=DocumentPreviewResponse)
async def preview_document(department: str, filename: str, current_user: User = Depends(get_current_user)):
    _require_folder(current_user.id, department)
    safe_name = safe_filename(filename)
    data = read_document_bytes(current_user.id, department, safe_name)
    if data is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    kind = Path(safe_name).suffix.lower().lstrip(".") or "bin"
    preview = (read_normalized_markdown(current_user.id, department, safe_name) or "").strip()[:500]
    if not preview:
        try:
            docs = await asyncio.to_thread(load_bytes, safe_name, data)
            preview = " ".join(doc.page_content for doc in docs).strip()[:500]
        except ParseError:
            preview = ""
    return DocumentPreviewResponse(filename=safe_name, kind=kind, preview=preview, size=len(data))


@app.get("/api/documents/{department}/{filename}/content")
async def document_content(department: str, filename: str, current_user: User = Depends(get_current_user)):
    _require_folder(current_user.id, department)
    safe_name = safe_filename(filename)
    data = read_document_bytes(current_user.id, department, safe_name)
    if data is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    media_types = {
        ".pdf": "application/pdf",
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
        ".markdown": "text/markdown; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".htm": "text/html; charset=utf-8",
        ".json": "application/json",
        ".csv": "text/csv; charset=utf-8",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }
    media_type = media_types.get(Path(safe_name).suffix.lower(), "application/octet-stream")
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


@app.post("/api/documents/{department}/{filename}/move")
async def move_document(
    department: str,
    filename: str,
    payload: DocumentMoveRequest,
    current_user: User = Depends(get_current_user),
):
    _require_folder(current_user.id, department)
    _require_folder(current_user.id, payload.target)
    if payload.target == department:
        return {"status": "ok", "filename": filename, "department": payload.target}
    safe_name = safe_filename(filename)
    data = read_document_bytes(current_user.id, department, safe_name)
    if data is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    if any(item["name"] == safe_name for item in document_rows(current_user.id, payload.target)):
        raise HTTPException(status_code=400, detail="目标文件夹已有同名文件")
    status = get_status(current_user.id, department, safe_name)
    save_document_bytes(
        current_user.id,
        payload.target,
        safe_name,
        data,
        status=(status or {}).get("status") or "indexed",
        content_hash=None,
        error=(status or {}).get("error"),
    )
    clear_status(current_user.id, department, safe_name)
    _remove_disk_copy(department, safe_name)
    return {"status": "ok", "filename": safe_name, "department": payload.target}


def _remove_disk_copy(department: str, filename: str) -> None:
    target = Path(KNOWLEDGE_BASE_DIR) / department / filename
    if target.is_file():
        target.unlink()