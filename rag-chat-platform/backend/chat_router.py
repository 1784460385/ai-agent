"""聊天路由:Web 关注点。

只负责 FastAPI 路由 + Form/File 解析 + StreamingResponse 包装,
业务逻辑在 chat_service.py。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from chat_service import make_event_stream, prepare_chat_request
from keys_router import resolve_api_key
from models_db import User
from auth import get_current_user

router = APIRouter()


@router.post("/api/chat")
async def chat_endpoint(
    message: str = Form(""),
    conversation_id: int | None = Form(None),
    api_key_id: int = Form(...),
    files: list[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_user),
):
    """RAG 问答:SSE 流式返回。可续聊 conversation_id,可附文件或图片。"""
    api_key, model_name, base_url = resolve_api_key(current_user.id, api_key_id)

    payloads: list[tuple[str, bytes]] = []
    for upload in files or []:
        if not upload.filename:
            continue
        payloads.append((upload.filename, await upload.read()))

    prepared = await prepare_chat_request(
        user_id=current_user.id,
        api_key_id=api_key_id,
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        message=message,
        files_payload=payloads,
        conversation_id=conversation_id,
    )

    return StreamingResponse(
        make_event_stream(prepared),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )