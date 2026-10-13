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
from fastapi.responses import JSONResponse, Response, StreamingResponse
from openai import APIStatusError, AsyncOpenAI, AuthenticationError
from starlette.requests import Request

from admin_router import router as admin_router
from auth import authenticate_token, ensure_admin, get_current_user
from auth_router import router as auth_router
from chat_attachments import AttachmentError, compose_user_text, prepare_attachments, vision_model
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
from database import document_rows, init_db, isolate_folders, read_document_bytes, save_document_bytes
from file_parsers import ParseError, load_bytes
from folders import create_folder, delete_folder, get_folder, list_folders, rename_folder, sync_from_disk
from history_router import backfill_conversations, open_conversation, prior_messages, save_chat_history
from history_router import router as history_router
from history_router import threads as thread_router
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
from rag_engine import build_rag_prompt, index_knowledge_base, ingest_saved_file
from vector_store import collection_count, delete_folder_collection, department_count, search_departments
from router import route_query

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    admin_id = ensure_admin()
    isolate_folders(admin_id)
    sync_from_disk(admin_id)
    backfill_conversations()
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
app.include_router(thread_router)


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
async def stats(current_user: User = Depends(get_current_user)):
    chunks = await asyncio.to_thread(collection_count, current_user.id)
    return StatsResponse(chunks=chunks)


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


@app.post("/api/chat")
async def chat_endpoint(
    message: str = Form(""),
    conversation_id: int | None = Form(None),
    api_key: str = Form(...),
    base_url: str = Form(DEEPSEEK_BASE_URL),
    model_name: str = Form(DEFAULT_MODEL),
    files: list[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_user),
):
    """RAG 问答接口：检索 → 增强 → 流式生成。可附带文档或图片。"""
    api_key = api_key.strip()
    if not api_key:
        raise HTTPException(status_code=401, detail="缺少 API Key")
    question = message.strip()
    if len(question) > 4000:
        raise HTTPException(status_code=400, detail="问题超过 4000 字")
    payloads: list[tuple[str, bytes]] = []
    for upload in files or []:
        if not upload.filename:
            continue
        payloads.append((upload.filename, await upload.read()))
    if not question and not payloads:
        raise HTTPException(status_code=400, detail="请输入问题或添加附件")
    try:
        prepared = await asyncio.to_thread(prepare_attachments, payloads)
    except AttachmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if prepared["images"] and not vision_model(model_name):
        raise HTTPException(status_code=400, detail="当前模型不能识别图片，请改为 deepseek-flash")
    user_text = compose_user_text(question, prepared["document_text"])
    stored_question = question or "请根据附件回答"
    user_id = current_user.id
    if conversation_id is not None:
        try:
            open_conversation(user_id, conversation_id, stored_question)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="对话不存在") from exc
    history = prior_messages(user_id, conversation_id)

    target_departments, via = await route_query(
        query=question or stored_question,
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        user_id=user_id,
    )
    router_payload = {
        "type": "router",
        "via": via,
        "departments": [
            {"key": dept, "name": (get_folder(user_id, dept) or {}).get("name", dept)} for dept in target_departments
        ],
    }

    try:
        hits = await asyncio.to_thread(
            search_departments, user_id, target_departments, question or stored_question, RETRIEVAL_TOP_K
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"知识库检索失败: {_safe_error(exc, api_key)}")

    labeled_docs = [f"[来源: {hit['source']}]\n{hit['content']}" for hit in hits]
    system_prompt = build_rag_prompt(stored_question, labeled_docs)
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
    user_content: str | list = user_text
    if prepared["images"]:
        user_content = [{"type": "text", "text": user_text}]
        user_content.extend(
            {"type": "image_url", "image_url": {"url": image["data_url"], "detail": "high"}}
            for image in prepared["images"]
        )

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url or DEEPSEEK_BASE_URL,
        max_retries=0,
        timeout=90,
    )

    try:
        stream = await client.chat.completions.create(
            model=model_name or DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": user_content},
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

    try:
        conversation = open_conversation(user_id, conversation_id, _redact(stored_question, api_key))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="对话不存在") from exc

    async def event_stream():
        parts: list[str] = []
        error_message: str | None = None
        finished = False
        try:
            yield _sse({"type": "conversation", "id": conversation["id"], "title": conversation["title"]})
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
                    _redact(stored_question, api_key),
                    _redact(content, api_key),
                    citations,
                    [item["name"] for item in router_payload["departments"]],
                    conversation["id"],
                    prepared["records"],
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
async def index_endpoint(department: str | None = Query(default=None), current_user: User = Depends(get_current_user)):
    """触发知识库重新索引。可只重建一个部门。"""
    if department is not None:
        _require_folder(current_user.id, department)
    try:
        result = await asyncio.to_thread(index_knowledge_base, current_user.id, department)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"索引失败: {exc}")
    return IndexResponse(**result)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    department: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """上传文档到当前用户的文件夹，并在后台解析、索引。"""
    _require_folder(current_user.id, department)
    filename = _safe_filename(file.filename)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    _check_payload(data, Path(filename).suffix.lower())

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
    safe_name = _safe_filename(filename)
    if read_document_bytes(current_user.id, department, safe_name) is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    set_status(current_user.id, department, safe_name, "parsing")
    background_tasks.add_task(ingest_saved_file, current_user.id, department, safe_name)
    return {"status": "parsing", "filename": safe_name, "department": department}


@app.delete("/api/documents/{department}/{filename}")
async def delete_document(department: str, filename: str, current_user: User = Depends(get_current_user)):
    """删除当前用户某个文件夹下的文档。删除后需要重建该文件夹索引。"""
    _require_folder(current_user.id, department)
    safe_name = _safe_filename(filename)
    if get_status(current_user.id, department, safe_name) is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    clear_status(current_user.id, department, safe_name)
    _remove_disk_copy(department, safe_name)
    return {"status": "ok", "filename": safe_name, "department": department}


@app.get("/api/documents/{department}/{filename}/preview", response_model=DocumentPreviewResponse)
async def preview_document(department: str, filename: str, current_user: User = Depends(get_current_user)):
    _require_folder(current_user.id, department)
    safe_name = _safe_filename(filename)
    data = read_document_bytes(current_user.id, department, safe_name)
    if data is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    kind = Path(safe_name).suffix.lower().lstrip(".") or "bin"
    preview = ""
    try:
        docs = await asyncio.to_thread(load_bytes, safe_name, data)
        preview = " ".join(doc.page_content for doc in docs).strip()[:500]
    except ParseError:
        preview = ""
    return DocumentPreviewResponse(filename=safe_name, kind=kind, preview=preview, size=len(data))


@app.get("/api/documents/{department}/{filename}/content")
async def document_content(department: str, filename: str, current_user: User = Depends(get_current_user)):
    _require_folder(current_user.id, department)
    safe_name = _safe_filename(filename)
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
    safe_name = _safe_filename(filename)
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
