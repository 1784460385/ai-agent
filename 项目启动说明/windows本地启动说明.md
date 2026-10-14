1. 需要先装好的软件
软件	版本	
Git  任意较新版本
Python 3.14  （本项目未使用conda）
Node.js  20 或以上

前端检查：
git --version
py -0p
node -v
npm -v

2. 拉取代码
git clone <仓库地址>
cd <仓库目录>\rag-chat-platform
仓库根目录下应能看到 backend 和 frontend 两个文件夹。

3. 启动后端（第一个 PowerShell 窗口）
国内网络建议先设 Hugging Face 镜像，否则首次下载 BAAI/bge-m3（约 2.1GB）很容易卡住：
cd rag-chat-platform\backend
$env:HF_ENDPOINT = "https://hf-mirror.com"
$env:HF_HUB_DISABLE_XET = "1"
# 用 3.14 建虚拟环境（不要直接打 python，以免进到 Anaconda 3.7）
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
如果 Activate.ps1 报执行策略错误执行代码：
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
重新启动：uvicorn main:app --reload --port 8000
看到类似 Uvicorn running on http://127.0.0.1:8000 即成功。
这个窗口不要关。

首次启动会：
自动创建 backend/app.db
自动创建管理员账号 admin / Aa123456
首次重建索引时下载 embedding 模型到 backend/models/
健康检查（另开窗口）：
curl http://127.0.0.1:8000/api/health
应返回 {"status":"ok"}。

4. 启动前端（第二个 PowerShell 窗口）
cd rag-chat-platform\frontend
npm install
npm run dev
看到 Local: http://localhost:5173/ 后，浏览器打开：

http://localhost:5173

开发服务器会把 /api 代理到后端 8000 端口，两个窗口都要保持运行。

5. 登录和使用
打开 http://localhost:5173
用 admin / Aa123456 登录
进入「知识库」：新建文件夹、上传 PDF/Word/Excel/图片 等、点「重建全部索引」
图片与扫描件会自动 OCR（首次较慢）；可用环境变量 OCR_ENABLED=0 关闭
进入「聊天」：在左侧填入自己的 DeepSeek API Key（sk- 开头）并保存，然后提问
说明：

API Key 只存在当前浏览器会话，刷新后要重新填，后端不保存
知识库页面改版后是左右分栏：左侧文件夹，右侧上传和文件列表
6. 日常再次启动
环境装好后，以后每次只要：

窗口 1：


cd rag-chat-platform\backend
$env:HF_ENDPOINT = "https://hf-mirror.com"
$env:HF_HUB_DISABLE_XET = "1"
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload --port 8000
窗口 2：


cd rag-chat-platform\frontend
npm run dev
7. 常见问题
python 是 3.7，pip 装不上
用 py -3.12（或你实际的 3.12+）创建 .venv，不要用 Anaconda 的 python。

8000 或 5173 端口被占用
关掉旧的 uvicorn / vite 窗口，或改端口。前端改端口后，后端 CORS 目前只允许 5173 / 5174。

首次索引很慢 / 下载停在 0 字节
确认启动后端前设置了 HF_ENDPOINT 和 HF_HUB_DISABLE_XET。

页面能开但接口失败
先确认后端窗口还在跑，再访问 http://127.0.0.1:8000/api/health。

不要提交、不要删除
.venv、node_modules、backend/app.db、backend/chroma_db、backend/models 都是本地数据，不要推进 Git。