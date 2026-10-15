# RAG 知识库 MCP Server — 使用说明

把 `rag-chat-platform` 的知识库问答能力接入 WorkBuddy。

```
WorkBuddy  →  rag_kb_mcp_server.py (MCP)  →  http://127.0.0.1:8000/api/*  →  RAG 后端
```

对应接口文档：`项目接口文档/RAG知识库问答-API接口文档-WorkBuddy-MCP.md`

---

## 一、前置条件

1. **RAG 后端已启动**，`http://127.0.0.1:8000/api/health` 返回 `status=ok`
2. **知识库里有已索引文档**（`parse_status=indexed`）
3. **已配置 DeepSeek API Key**（`/api/keys` 至少一条，且 `is_default=true`）

---

## 二、安装依赖

```bash
cd D:\Ai-Agent\rag-chat-platform\backend
.\.venv\Scripts\python.exe -m pip install "mcp>=1.0.0" httpx
```

> 复用后端已有 venv，避免重复安装 httpx。  
> 已验证版本：`mcp 2.3.0`。脚本同时兼容 mcp 1.x（FastMCP）与 2.x（MCPServer），无需改代码。

---

## 三、配置到 WorkBuddy

把 `mcp.json.template` 的内容**合并**进 WorkBuddy 的 MCP 配置文件：

**配置文件位置**：`C:\Users\<你的用户名>\.workbuddy\mcp.json`

> 注意文件名是 `mcp.json`（**没有**点前缀），不是 `.mcp.json`。

```json
{
  "mcpServers": {
    "rag-knowledge-base": {
      "command": "D:\\Ai-Agent\\rag-chat-platform\\backend\\.venv\\Scripts\\python.exe",
      "args": [
        "D:\\Ai-Agent\\rag-chat-platform\\mcp_server\\rag_kb_mcp_server.py"
      ],
      "env": {
        "KB_BASE_URL": "http://127.0.0.1:8000",
        "KB_USERNAME": "admin",
        "KB_PASSWORD": "Aa123456",
        "KB_TIMEOUT": "180"
      }
    }
  }
}
```

如果已有其他 MCP Server，把 `"rag-knowledge-base": {...}` 添加到现有 `mcpServers` 里即可。

---

## 四、激活

1. WorkBuddy 对话窗口**左下角「+」** → 「**连接器**」
2. 在连接器管理页面**右上角点「自定义连接器」**入口
3. 找到 `rag-knowledge-base`，点「**信任**」（必须手动点，配置不会自动生效）
4. 连接成功后，工具会出现在可用工具列表

---

## 五、提供的工具

| 工具 | HTTP | 用途 | 常用度 |
|------|------|------|--------|
| `kb_health` | `GET /api/health` | 探活 | 调试用 |
| `kb_config` | `GET /api/config` | 上传格式 / OCR 配置 | 低 |
| `kb_list_keys` | `GET /api/keys` | 列模型 Key，拿 `api_key_id` | 自动调用 |
| `kb_list_folders` | `GET /api/departments` | 列文件夹与文档 | 高频 |
| `kb_list_documents` | `GET /api/documents` | 只列文档 | 中 |
| **`kb_ask`** | **`POST /api/chat`** | **知识库问答（核心，SSE 聚合）** | **最高** |
| `kb_list_conversations` | `GET /api/conversations` | 对话线程列表 | 中 |
| `kb_get_conversation` | `GET /api/conversations/{id}` | 对话详情 | 中 |
| `kb_delete_conversation` | `DELETE /api/conversations/{id}` | 删除对话线程 | 低 |
| `kb_search_history` | `GET /api/history` | 扁平历史检索 | 中 |
| `kb_upload` | `POST /api/upload` | 上传文档 | 中 |
| `kb_retry_document` | `POST .../retry` | 重试解析失败文件 | 低 |
| `kb_delete_document` | `DELETE .../documents/...` | 删除文档 | 低 |
| `kb_move_document` | `POST .../move` | 移动文档 | 低 |
| `kb_preview_document` | `GET .../preview` | 预览文本 | 低 |
| `kb_reindex` | `POST /api/index` | 重建索引（约 1 次/分钟） | 中 |
| `kb_create_folder` | `POST /api/folders` | 新建文件夹 | 低 |
| `kb_rename_folder` | `PATCH /api/folders/{key}` | 重命名文件夹 | 低 |
| `kb_delete_folder` | `DELETE /api/folders/{key}` | 删除文件夹 | 低 |
| `kb_stats` | `GET /api/stats` | 向量片段统计 | 低 |

未封装（可按需扩展）：登录改密、keys CRUD、admin、清空 history、下载原文 content。

---

## 六、内建的关键处理

| 能力 | 实现 |
|------|------|
| Token 缓存 + 401 自动重登 | `TokenManager`，线程安全；HTTP / SSE 均只重试一次 |
| 默认 Key 自动选取 | `kb_ask` 不传 `api_key_id` 时取 `is_default=true` |
| SSE 聚合为同步 JSON | `_consume_sse()` 拼接全部 `delta`，返回 `answer` |
| 保留 `conversation_id` | 返回给上游，多轮时回传 |
| 返回 `sources` / `router` | 含 department / department_name 等字段 |
| 流内 `error` | `ok:false` + 已拼接的部分 `answer` |
| 限速 429 | 透传 `detail` 与 `retry_after`（chat/upload/index/login） |
| 超时 | 默认 180s，可用 `KB_TIMEOUT` 调整；重建索引至少 600s |

---

## 七、验证流程

```bash
# 1. 确保后端已启动
curl http://127.0.0.1:8000/api/health

# 2. 手动测试 MCP Server 能否启动（会等 stdin，Ctrl+C 退出）
D:\Ai-Agent\rag-chat-platform\backend\.venv\Scripts\python.exe ^
  D:\Ai-Agent\rag-chat-platform\mcp_server\rag_kb_mcp_server.py
```

在 WorkBuddy 对话里依次测试：

```
1. "检查知识库服务是否正常"          → 应调用 kb_health
2. "知识库里有哪些文件夹和文档？"      → 应调用 kb_list_folders
3. "年假有几天？"                    → 应调用 kb_ask，返回答案 + 引用来源
4. "刚才那个问题的引用来自哪个文件？"   → 多轮，应带上 conversation_id
```

---

## 八、常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 登录失败 | 用户名密码错 | 改 `KB_USERNAME`/`KB_PASSWORD` |
| 401 循环 | 账号被禁用 | 检查 `/api/admin/users` 里 `is_active` |
| 问答超时 | 模型冷启动 | 重试，或调大 `KB_TIMEOUT` |
| HTTP 429 | 触发限速 | 看 `retry_after`，稍后再试 |
| "暂无可用 Key" | 没配 DeepSeek Key | 先在 Web UI 配 Key |
| 回答"无法回答" | 知识库无相关内容 | 上传文档 + 等 `indexed` 或 `kb_reindex` |
| 上传后查不到 | 异步解析未完成 | 等几秒再 `kb_list_folders` |
| 解析失败 | 格式/损坏 | `kb_retry_document` 或检查 `parse_error` |

---

## 九、扩展方向

跑通之后，可以基于这些工具做：

- **企业微信/飞书机器人**：知识库问答结果自动推送到群里
- **定时知识简报**：每天自动汇总某文件夹的新增内容
- **批量导入**：遍历本地目录，自动 `kb_upload` + `kb_reindex`
- **问答审计**：定期 `kb_search_history` 分析高频问题，反哺知识库
