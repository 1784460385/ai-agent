"""
RAG 知识库问答平台 — WorkBuddy MCP Server
=========================================

把 rag-chat-platform 的知识库问答能力封装成 MCP Tools，供 WorkBuddy 调用。

对应接口文档：项目接口文档/RAG知识库问答-API接口文档-WorkBuddy-MCP.md

依赖：
    pip install "mcp[cli]" httpx

运行（stdio 模式，供 WorkBuddy 启动）：
    由 WorkBuddy 通过 mcp.json 自动拉起，一般无需手动运行。
    手动调试可用：
        python rag_kb_mcp_server.py

环境变量（在 mcp.json 的 env 中配置）：
    KB_BASE_URL    后端地址，默认 http://127.0.0.1:8000
    KB_USERNAME    登录用户名，默认 admin
    KB_PASSWORD    登录密码，默认 Aa123456
    KB_TIMEOUT     HTTP 超时秒数，默认 180（问答含检索+生成，需较长超时）
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any
from urllib.parse import quote

import httpx

# 兼容 mcp 1.x（FastMCP）与 2.x（MCPServer）
try:
    from mcp.server.mcpserver import MCPServer as _Server  # mcp >= 2.0
except ImportError:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP as _Server  # mcp 1.x

# ============================================================
# 配置
# ============================================================
BASE_URL = os.getenv("KB_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USERNAME = os.getenv("KB_USERNAME", "admin")
PASSWORD = os.getenv("KB_PASSWORD", "Aa123456")
TIMEOUT = float(os.getenv("KB_TIMEOUT", "180"))

API = f"{BASE_URL}/api"

mcp = _Server("rag-knowledge-base")


# ============================================================
# 鉴权：Token 自动管理（缓存 + 401 自动重登）
# ============================================================
class TokenManager:
    """线程安全的 Token 管理器，401 时 clear 后强制重新登录"""

    def __init__(self) -> None:
        self._token: str | None = None
        self._user: dict | None = None
        self._lock = threading.Lock()

    def get(self) -> str:
        with self._lock:
            if self._token:
                return self._token
        return self.login()

    def login(self) -> str:
        """强制登录并刷新缓存（忽略已有 token）"""
        with self._lock:
            url = f"{API}/auth/login"
            with httpx.Client(timeout=30) as c:
                r = c.post(url, json={"username": USERNAME, "password": PASSWORD})
            if r.status_code == 429:
                raise RuntimeError(
                    f"登录过于频繁（HTTP 429）：{ _detail_of(r) }。"
                    f"请稍后再试（Retry-After={r.headers.get('Retry-After', '?')}）"
                )
            if r.status_code != 200:
                raise RuntimeError(
                    f"登录失败（HTTP {r.status_code}）：{_detail_of(r)}。"
                    f"请检查 KB_USERNAME / KB_PASSWORD 配置"
                )
            data = r.json()
            self._token = data["access_token"]
            self._user = data.get("user")
            return self._token

    def clear(self) -> None:
        with self._lock:
            self._token = None

    @property
    def user(self) -> dict | None:
        return self._user


_tokens = TokenManager()


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_tokens.get()}"}


def _detail_of(r: httpx.Response) -> str:
    """解析 FastAPI detail（可能是 str 或校验错误 list）"""
    try:
        body = r.json()
    except Exception:
        return (r.text or "").strip() or f"HTTP {r.status_code}"
    detail = body.get("detail", body)
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if isinstance(item, dict):
                loc = ".".join(str(x) for x in item.get("loc", []) if x != "body")
                msg = item.get("msg") or str(item)
                parts.append(f"{loc}: {msg}" if loc else msg)
            else:
                parts.append(str(item))
        return "; ".join(parts) or str(detail)
    if isinstance(detail, dict):
        return json.dumps(detail, ensure_ascii=False)
    return str(detail)


def _err(r: httpx.Response) -> dict:
    """统一错误返回（含 429 Retry-After）"""
    result: dict[str, Any] = {
        "ok": False,
        "http_status": r.status_code,
        "error": _detail_of(r),
    }
    if r.status_code == 429:
        result["retry_after"] = r.headers.get("Retry-After")
    return result


def _ok(r: httpx.Response, data: Any = None) -> dict:
    if data is None:
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
    return {"ok": True, **data} if isinstance(data, dict) else {"ok": True, "data": data}


def _clean_params(**kwargs: Any) -> dict[str, Any]:
    """去掉 None / 空字符串，避免无意义 query 干扰后端"""
    out: dict[str, Any] = {}
    for key, value in kwargs.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        out[key] = value
    return out


def _path_segment(value: str) -> str:
    """路径参数编码（保留中文文件名可读性）"""
    return quote(str(value), safe="")


def _request(
    method: str,
    path: str,
    *,
    retry_on_401: bool = True,
    **kwargs: Any,
) -> httpx.Response:
    """统一请求入口：带鉴权头，遇 401 自动重登重试一次"""
    url = path if path.startswith("http") else f"{API}{path}"
    timeout = kwargs.pop("timeout", TIMEOUT)

    with httpx.Client(timeout=timeout) as c:
        r = c.request(method, url, headers=_headers(), **kwargs)
        if r.status_code == 401 and retry_on_401:
            _tokens.clear()
            r = c.request(method, url, headers=_headers(), **kwargs)
    return r


# ============================================================
# 工具 1：健康检查
# ============================================================
@mcp.tool()
def kb_health() -> dict:
    """
    检查 RAG 知识库服务是否可用。返回 status=ok 表示正常。
    同时返回 device / reranker 等运行信息。
    建议在首次使用或排查问题时先调用。
    """
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{API}/health")
        if r.status_code == 200:
            return {"ok": True, "service": "reachable", **r.json()}
        return _err(r)
    except Exception as e:
        return {"ok": False, "error": f"无法连接后端 {BASE_URL}：{e}"}


# ============================================================
# 工具 2：运行时配置
# ============================================================
@mcp.tool()
def kb_config() -> dict:
    """
    获取上传格式、OCR 开关等运行时配置。
    上传前可用来确认支持的扩展名与大小上限。
    """
    try:
        r = _request("GET", "/config")
        if r.status_code != 200:
            return _err(r)
        return _ok(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# 工具 3：列出模型 API Key 配置
# ============================================================
@mcp.tool()
def kb_list_keys() -> dict:
    """
    列出当前用户已配置的模型 API Key（已脱敏）。
    返回的 id 即 api_key_id，是调用 kb_ask 问答的必填参数。
    优先使用 is_default=true 的那一条。
    """
    try:
        r = _request("GET", "/keys")
        if r.status_code != 200:
            return _err(r)
        data = r.json()
        items = data.get("items", [])
        default = next((i for i in items if i.get("is_default")), None)
        return {
            "ok": True,
            "count": len(items),
            "default_api_key_id": default["id"] if default else None,
            "items": items,
            "hint": (
                f"建议使用 api_key_id={default['id']}"
                if default
                else "尚无可用 Key，请先在 Web UI 的「模型配置」里添加 DeepSeek API Key"
            ),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# 工具 4：列出知识库文件夹与文档
# ============================================================
@mcp.tool()
def kb_list_folders() -> dict:
    """
    列出知识库中所有文件夹及其包含的文档。
    返回每个文件夹的 key、名称、向量片段数 chunk_count，以及文件列表。
    可用于确认知识库里有哪些内容、哪些文档已完成索引（parse_status=indexed）。
    """
    try:
        r = _request("GET", "/departments")
        if r.status_code != 200:
            return _err(r)
        data = r.json()
        depts = data.get("departments", [])
        summary = []
        for d in depts:
            files = d.get("files", [])
            summary.append({
                "key": d.get("key"),
                "name": d.get("name"),
                "chunk_count": d.get("chunk_count", 0),
                "file_count": len(files),
                "indexed_count": sum(
                    1 for f in files if f.get("parse_status") == "indexed"
                ),
                "failed_count": sum(
                    1 for f in files if f.get("parse_status") == "failed"
                ),
            })
        return {
            "ok": True,
            "folder_count": len(depts),
            "overview": summary,
            "departments": depts,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# 工具 5：仅列出文档
# ============================================================
@mcp.tool()
def kb_list_documents(department: str | None = None) -> dict:
    """
    列出知识库中的文档文件。

    Args:
        department: 可选，按文件夹 key 过滤，如 "hr"。不传则返回全部。
    """
    try:
        r = _request("GET", "/documents")
        if r.status_code != 200:
            return _err(r)
        files = r.json().get("files", [])
        if department:
            files = [f for f in files if f.get("department") == department]
        return {"ok": True, "count": len(files), "files": files}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# 工具 6：核心 —— 知识库问答（消费 SSE 并聚合）
# ============================================================
def _consume_sse(r: httpx.Response) -> dict:
    """逐行消费 SSE 流，聚合 delta 文本，收集 conversation/router/sources"""
    answer_parts: list[str] = []
    conversation_id: int | None = None
    title: str = ""
    router: dict = {}
    sources: list = []
    error_msg: str | None = None
    finished = False

    for line in r.iter_lines():
        if not line:
            continue
        line = line.strip() if isinstance(line, str) else line.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            evt = json.loads(payload)
        except json.JSONDecodeError:
            continue

        etype = evt.get("type")
        if etype == "conversation":
            conversation_id = evt.get("id")
            title = evt.get("title", "")
        elif etype == "router":
            router = {
                "via": evt.get("via"),
                "departments": evt.get("departments", []),
            }
        elif etype == "sources":
            sources = evt.get("sources", [])
        elif etype == "delta":
            content = evt.get("content") or ""
            if content:
                answer_parts.append(content)
        elif etype == "error":
            error_msg = evt.get("message", "生成过程出错")
        elif etype == "done":
            finished = True
            break

    result: dict[str, Any] = {
        "ok": error_msg is None,
        "conversation_id": conversation_id,
        "title": title,
        "answer": "".join(answer_parts),
        "router": router,
        "sources": sources,
        "finished": finished and error_msg is None,
    }
    if error_msg:
        result["error"] = error_msg
        # 即使出错也保留已拼接文本，便于上游 Agent 使用部分结果
    return result


@mcp.tool()
def kb_ask(
    message: str,
    api_key_id: int | None = None,
    conversation_id: int | None = None,
) -> dict:
    """
    向知识库提问，返回完整回答与引用来源。这是核心工具。

    Args:
        message: 问题文本，最长 4000 字
        api_key_id: 模型配置 id。不传则自动使用默认 Key（is_default=true）
        conversation_id: 续聊时传入上一轮返回的 conversation_id，实现多轮对话

    返回：
        answer          完整回答文本
        conversation_id 对话 id，多轮对话时回传
        router          命中的知识库文件夹（via=rule|llm, departments）
        sources         检索引用（index/source/department/department_name/preview/excerpt）
        finished        是否正常收到 done 事件
    """
    if not message or not message.strip():
        return {"ok": False, "error": "问题不能为空"}
    if len(message) > 4000:
        return {"ok": False, "error": f"问题超长（{len(message)} 字），最长 4000 字"}

    if api_key_id is None:
        keys = kb_list_keys()
        if not keys.get("ok"):
            return keys
        api_key_id = keys.get("default_api_key_id")
        if api_key_id is None:
            return {
                "ok": False,
                "error": "知识库暂无可用模型 Key，请先在 Web UI「模型配置」中添加 DeepSeek API Key",
            }

    form = {"message": message, "api_key_id": str(api_key_id)}
    if conversation_id is not None:
        form["conversation_id"] = str(conversation_id)

    def _once(*, retried: bool) -> dict:
        try:
            with httpx.Client(timeout=TIMEOUT) as c:
                with c.stream(
                    "POST",
                    f"{API}/chat",
                    headers=_headers(),
                    data=form,  # Form 字段：application/x-www-form-urlencoded，后端 Form() 可接受
                ) as r:
                    if r.status_code == 401 and not retried:
                        _tokens.clear()
                        _tokens.login()
                        return _once(retried=True)
                    if r.status_code != 200:
                        r.read()
                        return _err(r)
                    return _consume_sse(r)
        except httpx.ReadTimeout:
            return {
                "ok": False,
                "error": f"问答超时（>{TIMEOUT}s）。可能是模型冷启动或限速，请稍后重试",
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return _once(retried=False)


# ============================================================
# 工具 7：对话线程
# ============================================================
@mcp.tool()
def kb_list_conversations(keyword: str = "") -> dict:
    """
    列出历史对话线程（最多 200 条，按更新时间倒序）。
    返回字段为 items:[{id, title, updated_at}]。

    Args:
        keyword: 可选，按标题关键词搜索
    """
    try:
        r = _request(
            "GET",
            "/conversations",
            params=_clean_params(keyword=keyword),
        )
        if r.status_code != 200:
            return _err(r)
        return _ok(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def kb_get_conversation(thread_id: int) -> dict:
    """
    获取某个对话的完整消息记录（含问答、引用来源、附件元数据）。

    Args:
        thread_id: 对话 id
    """
    try:
        r = _request("GET", f"/conversations/{thread_id}")
        if r.status_code != 200:
            return _err(r)
        return _ok(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def kb_delete_conversation(thread_id: int) -> dict:
    """
    删除某个对话线程，并级联删除其中的问答记录。

    Args:
        thread_id: 对话 id
    """
    try:
        r = _request("DELETE", f"/conversations/{thread_id}")
        if r.status_code != 200:
            return _err(r)
        return _ok(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def kb_search_history(keyword: str = "", page: int = 1, size: int = 20) -> dict:
    """
    分页检索历史问答记录（扁平列表，含问题、回答、引用）。
    注意：清空扁平历史不会删除对话线程。

    Args:
        keyword: 搜索关键词（匹配 question）
        page: 页码，从 1 开始
        size: 每页条数，1–100
    """
    try:
        size = max(1, min(int(size), 100))
        page = max(1, int(page))
        r = _request(
            "GET",
            "/history",
            params=_clean_params(page=page, size=size, keyword=keyword),
        )
        if r.status_code != 200:
            return _err(r)
        return _ok(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# 工具 8：上传 / 文档管理
# ============================================================
@mcp.tool()
def kb_upload(file_path: str, department: str) -> dict:
    """
    上传一个本地文档到知识库的指定文件夹，后台自动解析并索引。

    Args:
        file_path: 本地文件的绝对路径，如 "D:/docs/年假制度.pdf"
        department: 目标文件夹 key（可用 kb_list_folders 查询），如 "hr"

    注意：上传后为异步解析，需稍后调用 kb_list_folders 查看 parse_status。
         解析失败可用 kb_retry_document；删除后建议 kb_reindex。
    """
    if not os.path.isfile(file_path):
        return {"ok": False, "error": f"文件不存在：{file_path}"}
    if not department or not department.strip():
        return {"ok": False, "error": "department（文件夹 key）不能为空"}

    filename = os.path.basename(file_path)
    try:
        with open(file_path, "rb") as fh:
            files = {"file": (filename, fh)}
            r = _request(
                "POST",
                "/upload",
                data={"department": department.strip()},
                files=files,
            )
        if r.status_code != 200:
            return _err(r)
        data = r.json()
        return {
            "ok": True,
            **data,
            "hint": "后台异步解析中，请稍后用 kb_list_folders 查看 parse_status=indexed",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def kb_retry_document(department: str, filename: str) -> dict:
    """
    重新解析并索引一个失败的文件。

    Args:
        department: 文件夹 key
        filename: 文件名
    """
    try:
        path = f"/documents/{_path_segment(department)}/{_path_segment(filename)}/retry"
        r = _request("POST", path)
        if r.status_code != 200:
            return _err(r)
        return _ok(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def kb_delete_document(department: str, filename: str) -> dict:
    """
    删除指定文件夹下的文档。删除后建议对该文件夹执行 kb_reindex。

    Args:
        department: 文件夹 key
        filename: 文件名
    """
    try:
        path = f"/documents/{_path_segment(department)}/{_path_segment(filename)}"
        r = _request("DELETE", path)
        if r.status_code != 200:
            return _err(r)
        return {
            "ok": True,
            **r.json(),
            "hint": f"建议执行 kb_reindex(department=\"{department}\") 同步向量库",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def kb_move_document(department: str, filename: str, target: str) -> dict:
    """
    将文档移动到另一个文件夹。

    Args:
        department: 源文件夹 key
        filename: 文件名
        target: 目标文件夹 key
    """
    if not target or not target.strip():
        return {"ok": False, "error": "target（目标文件夹 key）不能为空"}
    try:
        path = f"/documents/{_path_segment(department)}/{_path_segment(filename)}/move"
        r = _request("POST", path, json={"target": target.strip()})
        if r.status_code != 200:
            return _err(r)
        return _ok(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def kb_preview_document(department: str, filename: str) -> dict:
    """
    预览文档前约 500 字文本与文件大小。

    Args:
        department: 文件夹 key
        filename: 文件名
    """
    try:
        path = f"/documents/{_path_segment(department)}/{_path_segment(filename)}/preview"
        r = _request("GET", path)
        if r.status_code != 200:
            return _err(r)
        return _ok(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# 工具 9：重建索引
# ============================================================
@mcp.tool()
def kb_reindex(department: str | None = None) -> dict:
    """
    重建知识库向量索引。上传/删除文档后建议执行。
    注意：全量重建限速约 1 次/分钟，过于频繁会返回 429。

    Args:
        department: 可选，只重建指定文件夹；不传则重建全部
    """
    try:
        params = _clean_params(department=department)
        r = _request(
            "POST",
            "/index",
            params=params or None,
            timeout=max(TIMEOUT, 600),
        )
        if r.status_code != 200:
            return _err(r)
        return _ok(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# 工具 10：文件夹 CRUD
# ============================================================
@mcp.tool()
def kb_create_folder(name: str) -> dict:
    """
    在知识库中新建一个文件夹。

    Args:
        name: 文件夹名称，如 "法务部"（1–40 字，不能含 \\ / : * ? \" < > |）
    """
    try:
        r = _request("POST", "/folders", json={"name": name})
        if r.status_code not in (200, 201):
            return _err(r)
        return _ok(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def kb_rename_folder(folder_key: str, name: str) -> dict:
    """
    重命名知识库文件夹（key 不变，只改显示名）。

    Args:
        folder_key: 文件夹 key
        name: 新名称
    """
    try:
        r = _request(
            "PATCH",
            f"/folders/{_path_segment(folder_key)}",
            json={"name": name},
        )
        if r.status_code != 200:
            return _err(r)
        return _ok(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def kb_delete_folder(folder_key: str) -> dict:
    """
    删除知识库文件夹及其向量集合。不可恢复，请谨慎。

    Args:
        folder_key: 文件夹 key
    """
    try:
        r = _request("DELETE", f"/folders/{_path_segment(folder_key)}")
        if r.status_code != 200:
            return _err(r)
        return _ok(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# 工具 11：索引统计
# ============================================================
@mcp.tool()
def kb_stats() -> dict:
    """
    查看当前用户知识库的向量片段统计（chunks 数量）。
    """
    try:
        r = _request("GET", "/stats")
        if r.status_code != 200:
            return _err(r)
        return _ok(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# 启动
# ============================================================
if __name__ == "__main__":
    # mcp 2.x 用 run_stdio_async；1.x 用 run(transport="stdio")
    if hasattr(mcp, "run_stdio_async"):
        import anyio

        anyio.run(mcp.run_stdio_async)
    else:  # pragma: no cover
        mcp.run(transport="stdio")
