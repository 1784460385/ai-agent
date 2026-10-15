# RAG 知识库问答平台 — API 接口文档（WorkBuddy MCP 对接版）

> 版本：与当前仓库 `rag-chat-platform` 后端代码一致（2026-10 更新）  
> 协议：HTTP / HTTPS + JSON；聊天为 SSE（`text/event-stream`）  
> 目标读者：腾讯 WorkBuddy / MCP Server 开发方、前端与集成方  
> OpenAPI 在线文档：服务启动后访问 `http://{host}:8000/docs`

---

## 1. 服务概述

本服务是一套**本地/私有化部署的知识库问答 API**：

1. 用户登录后获得 JWT  
2. 在「模型配置」中保存 DeepSeek API Key（服务端 Fernet 加密存储）  
3. 按文件夹管理知识库文档，上传后自动解析、分块、向量化  
4. 提问时自动路由到相关文件夹 → 检索 → RAG 增强 → 流式生成回答  

**推荐给 WorkBuddy / MCP 优先封装的能力：**

| 优先级 | 能力 | 对应接口 |
| --- | --- | --- |
| P0 | 登录拿 Token | `POST /api/auth/login` |
| P0 | 知识库问答（核心） | `POST /api/chat` |
| P0 | 列出文件夹 / 文档 | `GET /api/departments` |
| P1 | 上传文档 | `POST /api/upload` |
| P1 | 重建索引 | `POST /api/index` |
| P1 | 对话线程 / 扁平历史 | `GET /api/conversations`、`GET /api/history` |
| P1 | 模型 Key 列表 | `GET /api/keys` |
| P2 | 文件夹 CRUD、文档预览/删除/移动 | 见下文 |
| P2 | 管理员用户管理 | `/api/admin/*`（需 admin） |

---

## 2. 接入约定

### 2.1 Base URL

| 环境 | Base URL |
| --- | --- |
| 本地开发 | `http://127.0.0.1:8000` |
| 生产 | 由部署方提供，例如 `https://kb.example.com` |

所有业务路径均以 `/api` 开头。前端开发时代理会把 `/api` 代理到后端；**MCP / 外部调用请直连后端 Base URL**。

### 2.2 认证

除下列接口外，**所有 `/api/*` 请求必须带 Bearer Token**：

| 免鉴权 | 说明 |
| --- | --- |
| `GET /api/health` | 健康检查 |
| `POST /api/auth/login` | 登录 |
| `OPTIONS *` | CORS 预检 |

非 `/api` 路径（如 `/docs`、`/openapi.json`）不走登录中间件。

请求头：

```http
Authorization: Bearer <access_token>
```

- Token 由登录接口返回，算法 HS256，默认有效期 **7 天**（环境变量 `JWT_EXPIRE_MINUTES`，默认 `10080`）
- 无效 / 过期 / 用户被禁用 → `401`，body：`{"detail":"无效的登录凭证"}`
- 默认管理员（首次启动自动创建）：用户名 `admin`，密码 `Aa123456`（生产务必修改）

### 2.3 通用错误格式

```json
{ "detail": "错误说明文字" }
```

对外文案经 `safe_strings.public_error` 统一，常见固定文案：

| key（内部） | 对外文案 |
| --- | --- |
| `auth_invalid_credentials` | 无效的登录凭证 |
| `api_key_invalid` | API Key 无效或未授权 |
| `rate_limited` / `model_rate_limited` | 请求过于频繁,请稍后再试 |
| `model_upstream` | 模型服务暂时不可用,请稍后再试 |
| `retrieval_failed` | 知识库检索失败,请稍后再试 |
| `conversation_missing` | 对话不存在 |
| `input_too_long` | 问题超过 4000 字 |
| `input_missing` | 请输入问题或添加附件 |
| `input_image_no_vision_model` | 当前模型不能识别图片，请改为 deepseek-flash |
| `internal_error` | 服务暂时不可用,请稍后再试 |

| HTTP | 含义 |
| --- | --- |
| 400 | 参数错误 / 业务校验失败 |
| 401 | 未登录或 Token / API Key 无效 |
| 403 | 无权限（如非管理员访问 `/api/admin`） |
| 404 | 资源不存在 |
| 413 | 上传文件超限 |
| 429 | 接口限速 |
| 500 | 服务内部错误（对外多为固定文案） |
| 502 | 上游模型服务错误（部分场景） |

### 2.4 Content-Type

| 场景 | Content-Type |
| --- | --- |
| JSON 接口 | `application/json` |
| 上传 / 聊天（含文件） | `multipart/form-data` |
| 聊天响应 | `text/event-stream` |

### 2.5 限速（进程内 Token Bucket）

| 路径 | 桶名 | 默认配额 |
| --- | --- | --- |
| `POST /api/chat` | `chat_stream` | 30 次/分钟 |
| `POST /api/auth/login` | `login` | 5 次/分钟 |
| `POST /api/upload` | `upload` | 10 次/分钟 |
| `POST /api/index` | `index` | 1 次/分钟 |

超限 → **429** `{"detail":"请求过于频繁,请稍后再试"}`，并带 `Retry-After` 响应头。  
身份优先级：Bearer Token 的 SHA256 前缀 → `X-Forwarded-For` → 客户端 IP。  
说明：多 worker / 多实例时各进程独立计数，生产多副本需外置限速。

### 2.6 CORS

开发环境默认允许：

- `http://localhost:5173` / `http://127.0.0.1:5173`
- `http://localhost:5174` / `http://127.0.0.1:5174`

生产部署需按实际前端域名调整。

---

## 3. MCP Tool 映射建议（给 WorkBuddy）

仓库内已提供参考实现：`rag-chat-platform/mcp_server/rag_kb_mcp_server.py`。

### 3.1 建议 / 已实现 Tool 清单

参考实现：`rag-chat-platform/mcp_server/rag_kb_mcp_server.py`

| MCP Tool | HTTP | 说明 |
| --- | --- | --- |
| `kb_health` | `GET /api/health` | 探活（MCP 侧可不登录） |
| `kb_config` | `GET /api/config` | 上传格式 / OCR 等运行时配置 |
| `kb_list_keys` | `GET /api/keys` | 列出模型配置，拿到 `api_key_id` |
| `kb_list_folders` | `GET /api/departments` | 列出知识库文件夹与文件 |
| `kb_list_documents` | `GET /api/documents` | 仅列文档（可按 department 过滤） |
| `kb_ask` | `POST /api/chat` | **核心问答**；消费 SSE 后汇总 |
| `kb_list_conversations` | `GET /api/conversations` | 对话线程列表（`items`） |
| `kb_get_conversation` | `GET /api/conversations/{id}` | 对话详情 |
| `kb_delete_conversation` | `DELETE /api/conversations/{id}` | 删除对话线程 |
| `kb_search_history` | `GET /api/history` | 扁平问答历史检索 |
| `kb_upload` | `POST /api/upload` | 上传文档到指定文件夹 |
| `kb_retry_document` | `POST .../retry` | 重试解析失败文件 |
| `kb_delete_document` | `DELETE .../documents/...` | 删除文档 |
| `kb_move_document` | `POST .../move` | 移动文档 |
| `kb_preview_document` | `GET .../preview` | 预览文本 |
| `kb_reindex` | `POST /api/index` | 重建索引（约 1 次/分钟） |
| `kb_create_folder` | `POST /api/folders` | 新建文件夹 |
| `kb_rename_folder` | `PATCH /api/folders/{key}` | 重命名文件夹 |
| `kb_delete_folder` | `DELETE /api/folders/{key}` | 删除文件夹 |
| `kb_stats` | `GET /api/stats` | 向量片段数 |

> 登录：参考 MCP 用环境变量账号调 `POST /api/auth/login` 缓存 JWT，一般不单独做成 Tool。  
> 未封装（可按需扩展）：admin、改密、keys CRUD、清空 history、下载原文 content。

### 3.2 典型调用顺序

```text
1. （服务端）login → 保存 access_token
2. kb_list_keys() → 取 is_default=true 的 id，记为 api_key_id
3. （可选）kb_list_folders() → 确认知识库有内容 / parse_status=indexed
4. kb_ask(message, api_key_id, conversation_id?) → 完整回答 + sources
```

### 3.3 `kb_ask` SSE 消费约定（重要）

`POST /api/chat` 返回 **SSE**，每帧形如：

```text
data: {"type":"...","...":...}

```

事件类型（见 `backend/events.py`）：

| type | 字段 | 含义 |
| --- | --- | --- |
| `conversation` | `id`, `title` | 当前对话（新对话时会新建） |
| `router` | `via`=`rule`\|`llm`, `departments:[{key,name}]` | 命中了哪些知识库文件夹 |
| `sources` | `sources[]` | 检索到的引用片段（有命中才发） |
| `delta` | `content` | 增量文本，需拼接 |
| `done` | — | 正常结束 |
| `error` | `message` | 生成过程出错 |

`sources[]` 单项：

| 字段 | 说明 |
| --- | --- |
| `index` | 序号（从 1） |
| `source` | 来源文件名 |
| `department` | 文件夹 key |
| `department_name` | 文件夹显示名 |
| `preview` | 短预览 |
| `excerpt` | 完整摘录 |

**MCP 侧建议行为：**

1. 按顺序读事件，把所有 `delta.content` 拼成 `answer`
2. 保留最后一次 `conversation.id`，供多轮继续传 `conversation_id`
3. 把 `sources`、`router` 一并返回给上游 Agent
4. 遇到 `error` 或连接中断时，用已拼接文本 + 错误信息作为结果
5. 若 WorkBuddy MCP 不适合长时间流式：在适配层缓冲到 `done` 再一次性返回（参考实现已这样做）

---

## 4. 接口明细

### 4.1 认证 Auth（tag: `auth`）

#### 4.1.1 登录

`POST /api/auth/login`（免鉴权，限速 5/min）

**Request**

```json
{
  "username": "admin",
  "password": "Aa123456"
}
```

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| username | string | 1–50 |
| password | string | 必填 |

**Response 200**

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "admin",
    "role": "admin"
  }
}
```

**错误**：`401` 用户名或密码错误；`403` 账号已被禁用；`429` 限速。

---

#### 4.1.2 当前用户

`GET /api/auth/me`

**Response 200**

```json
{ "id": 1, "username": "admin", "role": "admin" }
```

---

#### 4.1.3 修改密码

`POST /api/auth/change-password`

```json
{
  "old_password": "Aa123456",
  "new_password": "NewPass123"
}
```

| 字段 | 约束 |
| --- | --- |
| new_password | 6–72 字符 |

**Response**：`{"status":"ok"}`  
**错误**：`400` 原密码不正确。

---

### 4.2 系统

#### 4.2.1 健康检查

`GET /api/health`（免鉴权）

```json
{
  "status": "ok",
  "device": "cuda",
  "reranker_device": "cpu",
  "gpu": "...",
  "gpu_total_gb": 4.0,
  "memory_allocated_mb": 1234.5,
  "reranker": "ready:cpu"
}
```

| 字段 | 说明 |
| --- | --- |
| `device` | Embedding 设备 |
| `reranker_device` | 重排设备 |
| `reranker` | `disabled` / `loading` / `ready:<device>` / `failed` |
| `gpu*` | 仅 CUDA 相关时出现 |

---

#### 4.2.2 运行时配置

`GET /api/config`

```json
{
  "formats": [
    { "ext": ".pdf", "label": "PDF", "max_mb": 20 }
  ],
  "coming_soon": ["GIF"],
  "accept": ".pdf,.docx,.doc,.xlsx,...",
  "ocr_enabled": true,
  "image_max_mb": 20,
  "ocr_timeout_seconds": 180
}
```

**当前支持格式**：`.pdf` `.docx` `.doc` `.xlsx` `.xls` `.pptx` `.md` `.markdown` `.txt` `.html` `.htm` `.csv` `.json` `.ipynb` 及图片（`.jpg/.jpeg/.png/.webp/.bmp/.tif/.tiff`，走 OCR）。大小上限以本接口为准。

---

#### 4.2.3 索引统计

`GET /api/stats`

```json
{ "chunks": 1234 }
```

返回**当前用户**向量片段总数。

---

### 4.3 模型 API Key 管理（tag: `api-keys`）

前缀：`/api/keys`  
允许模型：`deepseek-flash` | `deepseek-chat` | `deepseek-reasoner`  
API Key 须以 `sk-` 开头；Base URL 须为 `http://` 或 `https://`。  
默认模型：`deepseek-flash`；默认 Base URL：`https://api.deepseek.com`。

> 聊天接口必须传已保存配置的 `api_key_id`，**不能**在聊天请求里传明文 Key。

#### 4.3.1 列表

`GET /api/keys`

```json
{
  "items": [
    {
      "id": 1,
      "name": "默认 DeepSeek",
      "masked_key": "sk-****abcd",
      "model": "deepseek-flash",
      "base_url": "https://api.deepseek.com",
      "is_default": true,
      "created_at": "2026-01-01T00:00:00"
    }
  ]
}
```

排序：默认优先，再按 `id` 升序。

---

#### 4.3.2 创建

`POST /api/keys`

```json
{
  "name": "我的 Key",
  "api_key": "sk-xxxxxxxx",
  "model": "deepseek-flash",
  "base_url": "https://api.deepseek.com"
}
```

首条自动 `is_default=true`。返回单条公开对象（同列表项）。

---

#### 4.3.3 更新

`PUT /api/keys/{key_id}`

| 字段 | 说明 |
| --- | --- |
| name | 必填 |
| api_key | 空字符串表示不改 Key |
| model / base_url | 同创建 |

---

#### 4.3.4 删除

`DELETE /api/keys/{key_id}`

```json
{ "status": "ok", "id": 1 }
```

若删除的是默认项，会自动把剩余最早一条设为默认。

---

#### 4.3.5 设为默认

`POST /api/keys/{key_id}/default`

返回更新后的 Key 公开对象。

---

### 4.4 知识库：文件夹与文档

概念：路径里的 `department` ≡ 文件夹 `key`。

#### 4.4.1 列出全部文档

`GET /api/documents`

```json
{
  "files": [
    {
      "name": "年假制度.pdf",
      "size": 102400,
      "department": "hr",
      "parse_status": "indexed",
      "parse_error": null
    }
  ]
}
```

`parse_status` 常见值：`parsing` / `indexed` / `failed` 等。

---

#### 4.4.2 按文件夹列出（推荐）

`GET /api/departments`

```json
{
  "departments": [
    {
      "key": "hr",
      "name": "人力资源",
      "description": "...",
      "chunk_count": 120,
      "files": [ /* DocumentInfo */ ]
    }
  ]
}
```

---

#### 4.4.3 新建文件夹

`POST /api/folders`

```json
{ "name": "法务部" }
```

成功返回文件夹对象（含 `user_id`、`key`、`name`、`description`、`keywords`、`collection` 等）。  
名称非法（含 `\ / : * ? " < > |`）或同名冲突 → `400`。

---

#### 4.4.4 重命名文件夹

`PATCH /api/folders/{folder_key}`

```json
{ "name": "新名称" }
```

---

#### 4.4.5 删除文件夹

`DELETE /api/folders/{folder_key}`

```json
{ "status": "ok", "key": "hr" }
```

会同时删除该文件夹对应的向量集合。

---

#### 4.4.6 上传文档

`POST /api/upload`  
`Content-Type: multipart/form-data`  
限速 10/min

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| department | form string | 文件夹 key，必填 |
| file | file | 文档文件，必填 |

**Response 200**

```json
{
  "status": "parsing",
  "filename": "年假制度.pdf",
  "department": "hr"
}
```

上传后**后台异步**解析与索引；客户端应轮询 `GET /api/departments` 看 `parse_status`。

校验要点：

- 空文件 → `400`
- 扩展名不支持 / 黑名单后缀 / 内容与扩展名不符 → `400`
- 超大小上限 → `413`
- 文件夹不存在 → `404`

---

#### 4.4.7 重建索引

`POST /api/index`  
Query：`department` 可选，不传则重建当前用户全部。  
限速 1/min

示例：`POST /api/index?department=hr`

```json
{
  "status": "ok",
  "chunks_indexed": 500,
  "message": "...",
  "departments": { "hr": 120, "finance": 80 }
}
```

文件夹不存在 → `404`；内部失败 → `500`（对外固定「服务暂时不可用…」）。

---

#### 4.4.8 重试解析失败文件

`POST /api/documents/{department}/{filename}/retry`

```json
{ "status": "parsing", "filename": "...", "department": "hr" }
```

---

#### 4.4.9 删除文档

`DELETE /api/documents/{department}/{filename}`

```json
{ "status": "ok", "filename": "...", "department": "hr" }
```

> 删除后建议对该文件夹再调一次 `/api/index`，以同步向量库。

---

#### 4.4.10 预览文本

`GET /api/documents/{department}/{filename}/preview`

```json
{
  "filename": "年假制度.pdf",
  "kind": "pdf",
  "preview": "前 500 字摘要...",
  "size": 102400
}
```

---

#### 4.4.11 下载/查看原文

`GET /api/documents/{department}/{filename}/content`

返回二进制流，带对应 `Content-Type` 与 `Content-Disposition: inline`。

---

#### 4.4.12 移动文档

`POST /api/documents/{department}/{filename}/move`

```json
{ "target": "tech" }
```

目标文件夹已有同名文件 → `400`。  
成功：`{"status":"ok","filename":"...","department":"<目标 key>"}`。

---

### 4.5 核心：知识库问答（SSE）

`POST /api/chat`  
`Content-Type: multipart/form-data`  
限速 30/min  
响应：`text/event-stream`，头：`Cache-Control: no-cache`、`Connection: keep-alive`、`X-Accel-Buffering: no`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| message | string | 条件 | 问题文本，最长 4000 字；可与附件二选一 |
| api_key_id | int | 是 | 来自 `/api/keys` 的配置 id |
| conversation_id | int | 否 | 续聊时传入；不传则新建对话 |
| files | file[] | 否 | 附件（文档/图片）；图片需视觉模型（`deepseek-flash`） |

**cURL 示例**

```bash
curl -N -X POST "http://127.0.0.1:8000/api/chat" \
  -H "Authorization: Bearer <token>" \
  -F "message=年假怎么申请？" \
  -F "api_key_id=1"
```

续聊：

```bash
curl -N -X POST "http://127.0.0.1:8000/api/chat" \
  -H "Authorization: Bearer <token>" \
  -F "message=那病假呢？" \
  -F "api_key_id=1" \
  -F "conversation_id=12"
```

**进入 SSE 前的 HTTP 错误（非流内）：**

| 码 | 条件 |
| --- | --- |
| 400 | 问题超长；无问题且无附件；附件校验失败；有图但模型非 vision |
| 404 | `conversation_id` 不存在；`api_key_id` 无权限 |
| 429 | 限速 |
| 500 | 检索失败；Key 解密失败等 |

**SSE 成功流示例（示意）：**

```text
data: {"type":"conversation","id":12,"title":"年假怎么申请？"}

data: {"type":"router","via":"rule","departments":[{"key":"hr","name":"人力资源"}]}

data: {"type":"sources","sources":[{"index":1,"source":"年假制度.pdf","department":"hr","department_name":"人力资源","preview":"...","excerpt":"..."}]}

data: {"type":"delta","content":"根据"}

data: {"type":"delta","content":"制度"}

data: {"type":"done"}
```

流结束后服务端会异步落库（出现 `error` 时也可能落部分内容）。

---

### 4.6 对话线程 Conversations（tag: `conversations`）

与扁平 `/api/history` 并存：线程按会话组织；历史按单轮问答扁平存储。

#### 4.6.1 列表

`GET /api/conversations`  
Query：`keyword` 可选（按 title LIKE，已转义 `%` `_`）

```json
{
  "items": [
    { "id": 12, "title": "年假怎么申请？", "updated_at": "2026-10-15T06:00:00Z" }
  ]
}
```

最多 200 条，按 `updated_at` 倒序。

---

#### 4.6.2 详情

`GET /api/conversations/{thread_id}`

```json
{
  "id": 12,
  "title": "年假怎么申请？",
  "updated_at": "2026-10-15T06:00:00Z",
  "messages": [
    {
      "role": "user",
      "content": "年假怎么申请？",
      "attachments": [{ "name": "截图.png", "kind": "image" }]
    },
    {
      "role": "assistant",
      "content": "...",
      "sources": [
        { "index": 1, "source": "年假制度.pdf", "preview": "...", "excerpt": "..." }
      ],
      "router": {
        "via": "rule",
        "departments": [{ "key": "hr", "name": "人力资源" }]
      }
    }
  ]
}
```

不存在 → `404`「对话不存在」。

---

#### 4.6.3 删除线程

`DELETE /api/conversations/{thread_id}`

级联删除该线程下的 `ChatHistory`。

```json
{ "status": "ok", "id": 12 }
```

---

### 4.7 扁平历史 History（tag: `history`）

#### 4.7.1 分页列表

`GET /api/history`  
Query：`page`（≥1，默认 1）、`size`（1–100，默认 20）、`keyword`（搜 question）

```json
{
  "total": 100,
  "page": 1,
  "size": 20,
  "items": [
    {
      "id": 1,
      "question": "年假怎么申请？",
      "answer": "...",
      "citations": [],
      "router_departments": ["hr"],
      "created_at": "2026-10-15T06:00:00Z"
    }
  ]
}
```

---

#### 4.7.2 单条详情

`GET /api/history/{history_id}`

字段同列表 item。不存在 → `404`「记录不存在」。

---

#### 4.7.3 删除单条

`DELETE /api/history/{history_id}`

```json
{ "status": "ok", "id": 1 }
```

---

#### 4.7.4 清空当前用户全部历史

`DELETE /api/history`

```json
{ "status": "ok" }
```

> **注意**：清空 history **不会**自动删除 Conversation 线程。

---

### 4.8 管理员 Admin（tag: `admin`）

整组路由依赖 `require_admin`；非 admin → `403`「需要管理员权限」。

#### 4.8.1 用户列表

`GET /api/admin/users`  
Query：`page`、`size`（同 history）

```json
{
  "total": 10,
  "page": 1,
  "size": 20,
  "items": [
    {
      "id": 1,
      "username": "admin",
      "role": "admin",
      "is_active": true,
      "created_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

---

#### 4.8.2 创建用户

`POST /api/admin/users` → **201**

```json
{
  "username": "alice",
  "password": "Pass1234",
  "role": "user"
}
```

| 字段 | 约束 |
| --- | --- |
| username | 3–50 |
| password | 6–72 |
| role | `admin` \| `user`，默认 `user` |

用户名已存在 → `400`。

---

#### 4.8.3 更新用户

`PUT /api/admin/users/{user_id}`

Body 均可选：`role`、`is_active`、`password`。  
不能禁用当前登录账号 → `400`。

---

#### 4.8.4 删除用户

`DELETE /api/admin/users/{user_id}`

会删除该用户各文件夹对应的向量 collection。  
不能删除当前登录账号 → `400`。

```json
{ "status": "ok", "id": 2 }
```

---

## 5. 端点总表

| Method | Path | Auth | 备注 |
| --- | --- | --- | --- |
| POST | `/api/auth/login` | 否 | 限速 5/min |
| GET | `/api/auth/me` | Bearer | |
| POST | `/api/auth/change-password` | Bearer | |
| GET | `/api/admin/users` | Admin | |
| POST | `/api/admin/users` | Admin | 201 |
| PUT | `/api/admin/users/{user_id}` | Admin | |
| DELETE | `/api/admin/users/{user_id}` | Admin | |
| GET | `/api/keys` | Bearer | |
| POST | `/api/keys` | Bearer | |
| PUT | `/api/keys/{key_id}` | Bearer | |
| DELETE | `/api/keys/{key_id}` | Bearer | |
| POST | `/api/keys/{key_id}/default` | Bearer | |
| POST | `/api/chat` | Bearer | **SSE**；30/min |
| GET | `/api/conversations` | Bearer | |
| GET | `/api/conversations/{thread_id}` | Bearer | |
| DELETE | `/api/conversations/{thread_id}` | Bearer | |
| GET | `/api/history` | Bearer | |
| GET | `/api/history/{history_id}` | Bearer | |
| DELETE | `/api/history/{history_id}` | Bearer | |
| DELETE | `/api/history` | Bearer | 清空扁平历史 |
| GET | `/api/health` | **否** | |
| GET | `/api/config` | Bearer | |
| GET | `/api/stats` | Bearer | |
| GET | `/api/documents` | Bearer | |
| GET | `/api/departments` | Bearer | |
| POST | `/api/folders` | Bearer | |
| PATCH | `/api/folders/{folder_key}` | Bearer | |
| DELETE | `/api/folders/{folder_key}` | Bearer | |
| POST | `/api/index` | Bearer | 1/min |
| POST | `/api/upload` | Bearer | 10/min；multipart |
| POST | `/api/documents/{department}/{filename}/retry` | Bearer | |
| DELETE | `/api/documents/{department}/{filename}` | Bearer | |
| GET | `/api/documents/{department}/{filename}/preview` | Bearer | |
| GET | `/api/documents/{department}/{filename}/content` | Bearer | 二进制 |
| POST | `/api/documents/{department}/{filename}/move` | Bearer | |

**合计：约 35 个 HTTP 端点。**

---

## 6. 集成注意点（相对旧契约 / 典型 RAG API）

1. **聊天不是 JSON + 明文 `api_key`**：必须 `multipart/form-data` + 已保存的 `api_key_id`。`models.py` 里的 `ChatRequest` / `ModelConfig` 为遗留定义，**当前路由未使用**。
2. **对话列表字段名为 `items`**，不是 `conversations`。
3. **双轨历史**：`/api/conversations`（线程）与 `/api/history`（扁平）；清空 history 不删线程。
4. **SSE 自定义事件集**（`conversation` / `router` / `sources` / `delta` / `done` / `error`），不是 OpenAI 兼容 chunk，也没有 `[DONE]` 文本帧。
5. **上传异步**：立即返回 `status: parsing`，需轮询 `parse_status`。
6. **限速写在路径级**；多进程不共享桶。
7. **无平台级 API Key 鉴权**：只有用户 JWT + 用户侧 LLM Key。
8. **文件夹 = 多知识库路由**：`department` / `folder_key` 是同一概念。

---

## 7. 相关文件索引

| 路径 | 说明 |
| --- | --- |
| `rag-chat-platform/backend/main.py` | 应用入口、系统/知识库路由、鉴权中间件 |
| `rag-chat-platform/backend/chat_router.py` | `/api/chat` |
| `rag-chat-platform/backend/chat_service.py` | 问答编排与 SSE 事件 |
| `rag-chat-platform/backend/events.py` | SSE 事件类型常量 |
| `rag-chat-platform/backend/auth_router.py` | 登录 / me / 改密 |
| `rag-chat-platform/backend/keys_router.py` | 模型 Key CRUD |
| `rag-chat-platform/backend/history_router.py` | history + conversations |
| `rag-chat-platform/backend/admin_router.py` | 用户管理 |
| `rag-chat-platform/backend/rate_limit.py` | 限速 |
| `rag-chat-platform/backend/safe_strings.py` | 对外固定错误文案 |
| `rag-chat-platform/mcp_server/rag_kb_mcp_server.py` | WorkBuddy MCP 参考实现 |
| `rag-chat-platform/mcp_server/README.md` | MCP 启动说明 |
