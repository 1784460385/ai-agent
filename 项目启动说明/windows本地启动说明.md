# Windows 本地启动说明

适用于在本机开发运行 `rag-chat-platform`（FastAPI 后端 + Vite 前端）。

## 1. 环境

| 软件 | 要求 |
| --- | --- |
| Git | 较新即可 |
| Python | 3.12+（推荐 3.14；勿用 Anaconda 旧版） |
| Node.js | 20+ |

```powershell
git --version
py -0p
node -v
npm -v
```

## 2. 首次启动

仓库结构：`rag-chat-platform/backend`、`rag-chat-platform/frontend`。

### 后端（窗口 1）

国内网络先设 Hugging Face 镜像，否则首次下载 `BAAI/bge-m3`（约 2.1GB）容易卡住：

```powershell
cd D:\Ai-Agent\rag-chat-platform\backend
$env:HF_ENDPOINT = "https://hf-mirror.com"
$env:HF_HUB_DISABLE_XET = "1"

py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
# 若提示无法执行脚本：
# Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

python -m pip install -U pip
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

看到 `Uvicorn running on http://127.0.0.1:8000` 即成功。另开窗口检查：

```powershell
curl http://127.0.0.1:8000/api/health
```

首次启动会自动创建 `app.db`，并生成管理员账号 `admin` / `Aa123456`。

有 NVIDIA 显卡时，可按 `requirements.txt` 顶部注释先装 CUDA 版 PyTorch，再用 GPU 跑 embedding / 重排。

### 前端（窗口 2）

```powershell
cd D:\Ai-Agent\rag-chat-platform\frontend
npm install
npm run dev
```

打开 http://localhost:5173 。开发服务器会把 `/api` 代理到 `127.0.0.1:8000`。两个窗口都要保持运行。

## 3. 使用

1. 用 `admin` / `Aa123456` 登录（登录后请改密码）。
2. 打开「模型配置」，添加 DeepSeek API Key（`sk-` 开头）并设为默认；Key 加密保存在后端，按用户隔离。
3. 打开「知识库」：新建文件夹 → 上传文件 → 等待解析/索引完成（或点重建索引）。
4. 打开「聊天」提问；可点回形针或直接粘贴图片/文件作为附件。

知识库支持 PDF / Word / Excel / PPT / Markdown / TXT / HTML / CSV / JSON / Notebook / 图片等。图片与扫描件会 OCR（首次较慢）；关闭 OCR：`$env:OCR_ENABLED = "0"`。

## 4. 日常再次启动

```powershell
# 窗口 1
cd D:\Ai-Agent\rag-chat-platform\backend
$env:HF_ENDPOINT = "https://hf-mirror.com"
$env:HF_HUB_DISABLE_XET = "1"
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload --port 8000

# 窗口 2
cd D:\Ai-Agent\rag-chat-platform\frontend
npm run dev
```

## 5. 常见问题

| 问题 | 处理 |
| --- | --- |
| `python` 进了 Anaconda 3.7 | 用 `py -3.14 -m venv .venv`，激活后再装依赖 |
| `Activate.ps1` 无法运行 | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| 8000 / 5173 被占用 | 关掉旧的 uvicorn / vite；前端改端口后后端 CORS 目前允许 5173、5174 |
| 模型下载卡住 / 0 字节 | 启动前设置 `HF_ENDPOINT`、`HF_HUB_DISABLE_XET` |
| 页面开了但接口失败 | 确认后端在跑，访问 `/api/health` |
| OCR / 图片解析失败 | 确认已 `pip install -r requirements.txt`（含 rapidocr、onnxruntime、pymupdf） |

以下目录为本地数据，不要提交、不要误删：`.venv`、`node_modules`、`backend/app.db`、`backend/chroma_db`、`backend/models`。
