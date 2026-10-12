# 知识库问答

本地文档问答台：把 PDF、Markdown、TXT 写入 Chroma，提问时检索相关片段，再用你自己的 DeepSeek API Key 流式生成回答。API Key 只存在于单次请求里，后端不保存。

## 目录

```
rag-chat-platform/
├── backend/          FastAPI、分块、Chroma
└── frontend/         React + Vite 聊天界面
```

## 环境

- Python >= 3.12
- Node.js >= 20

默认模型是 `BAAI/bge-m3`，大约 2.1GB。首次索引会用系统 HTTP 把它下载到 `backend/models/`。国内网络请先设置镜像再启动后端：

```powershell
$env:HF_ENDPOINT = "https://hf-mirror.com"
$env:HF_HUB_DISABLE_XET = "1"
```

## 启动后端

```powershell
cd D:\Ai-Agent\rag-chat-platform\backend
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

当前机器上直接执行 `python` 会进到 Anaconda 3.7，装不上这套依赖。请用上面的 `py -3.14`。

## 启动前端

```powershell
cd D:\Ai-Agent\rag-chat-platform\frontend
npm install
npm run dev
```

打开 http://localhost:5173 。开发服务器会把 `/api` 代理到 `http://127.0.0.1:8000`。

## 使用

1. 在左侧输入 DeepSeek API Key（以 `sk-` 开头）。Key 只留在当前页面内存中，刷新后要重新填写。
2. `backend/knowledge_base/` 里已经放了 3 份示例文档，也可以继续上传 PDF、Markdown、TXT。
3. 点击「重建索引」。完成后每次提问都会检索最相关的 3 个片段。
4. 回答会逐段出现。资料里没有依据时，模型应回复「根据现有知识库，我无法回答这个问题」。

可先问这三句，用来核对示例文档：

- 客服邮箱是什么？
- 年假有几天？
- 超出免费额度怎么收费？

如果默认模型名 `deepseek-flash` 不被接口接受，在左侧改成 `deepseek-chat` 后再保存。

## 接口

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/api/chat` | 检索并流式回答。请求体含 `message` 与 `config.api_key` |
| POST | `/api/index` | 重建向量索引 |
| POST | `/api/upload` | 上传文档到知识库目录 |
| GET | `/api/documents` | 列出知识库文件 |
| GET | `/api/stats` | 当前片段数量 |
| GET | `/api/health` | 健康检查 |

聊天接口使用 JSON 格式的 SSE：`sources`、`delta`、`done`、`error`。这样文本里的换行不会把事件截断。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CHROMA_PERSIST_DIR` | `backend/chroma_db` | Chroma 持久化目录 |
| `KNOWLEDGE_BASE_DIR` | `backend/knowledge_base` | 原始文档目录 |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | 本地 Embedding 模型 |
| `CHUNK_SIZE` | `500` | 分块长度 |
| `CHUNK_OVERLAP` | `50` | 分块重叠 |
| `RETRIEVAL_TOP_K` | `3` | 检索条数 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek 地址 |
| `DEFAULT_MODEL` | `deepseek-flash` | 默认模型 |
