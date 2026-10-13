# Ubuntu 服务器部署与更新说明

本文档适用于在 Ubuntu 服务器上部署 `rag-chat-platform`，以及后续代码更新时的操作流程。

## 一、环境准备

### 1.1 系统要求

- Ubuntu 20.04 / 22.04 / 24.04
- Python 3.12+
- Node.js 20+
- Nginx
- 至少 2GB 可用磁盘（embedding 模型约 2GB）

### 1.2 安装系统依赖

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nodejs npm nginx git
```

如果系统自带的 Node.js 版本低于 20，用 NodeSource 安装新版：

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

验证：

```bash
python3 --version    # 应 >= 3.12
node -v              # 应 >= 20
npm -v
nginx -v
```

### 1.3 拉取代码

```bash
cd ~
git clone <你的仓库地址>.git ai-agent
cd ai-agent
```

后续更新只需 `git pull`，见第三节。

---

## 二、首次部署

假设项目路径为 `/home/jiahao/ai-agent/ai-agent/rag-chat-platform`，请按实际情况替换。

### 2.1 后端

#### 2.1.1 创建虚拟环境并安装依赖

```bash
cd /home/jiahao/ai-agent/ai-agent/rag-chat-platform/backend

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
deactivate
```

#### 2.1.2 配置 systemd 服务

创建 `/etc/systemd/system/rag-api.service`：

```bash
sudo tee /etc/systemd/system/rag-api.service > /dev/null <<'EOF'
[Unit]
Description=RAG chat API
After=network.target

[Service]
User=jiahao
WorkingDirectory=/home/jiahao/ai-agent/ai-agent/rag-chat-platform/backend
Environment=JWT_SECRET=请替换为一段随机字符串
Environment=HF_ENDPOINT=https://hf-mirror.com
Environment=HF_HUB_DISABLE_XET=1
ExecStart=/home/jiahao/ai-agent/ai-agent/rag-chat-platform/backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF
```

> 注意：
> - `User` 改成你的系统用户名。
> - `WorkingDirectory` 和 `ExecStart` 里的路径要和实际一致。
> - `JWT_SECRET` 用 `openssl rand -hex 32` 生成一段随机字符串，不要用默认值。

#### 2.1.3 启动后端

```bash
sudo systemctl daemon-reload
sudo systemctl enable rag-api
sudo systemctl start rag-api
sudo systemctl status rag-api
```

健康检查：

```bash
curl -s http://127.0.0.1:8000/api/health
# 应返回 {"status":"ok"}
```

首次启动会自动创建：
- `backend/app.db`（用户、文件夹、文档元数据）
- 默认管理员账号：`admin` / `Aa123456`（登录后请立即改密码）

### 2.2 前端

#### 2.2.1 构建静态文件

```bash
cd /home/jiahao/ai-agent/ai-agent/rag-chat-platform/frontend
npm install
npm run build
```

构建产物在 `frontend/dist/`。

#### 2.2.2 配置 Nginx

创建站点配置 `/etc/nginx/sites-available/rag-chat`：

```bash
sudo tee /etc/nginx/sites-available/rag-chat > /dev/null <<'EOF'
server {
    listen 90;
    server_name _;

    root /home/jiahao/ai-agent/ai-agent/rag-chat-platform/frontend/dist;
    index index.html;

    # 上传文件大小限制（知识库文件可能较大）
    client_max_body_size 50m;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Authorization $http_authorization;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
EOF
```

启用站点（建软链接到 `sites-enabled`）：

```bash
sudo ln -s /etc/nginx/sites-available/rag-chat /etc/nginx/sites-enabled/rag-chat
```

如果不需要默认站点，可以删掉它避免 80 端口冲突：

```bash
sudo rm /etc/nginx/sites-enabled/default
```

测试并重载：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

#### 2.2.3 防火墙放行

```bash
sudo ufw allow 90/tcp
sudo ufw reload
```

如果服务器在云上，还需要在云控制台的安全组里放行 90 端口。

### 2.3 访问验证

浏览器打开 `http://服务器IP:90`，用 `admin` / `Aa123456` 登录。

---

## 三、代码更新

每次从 GitHub 拉新代码后，按改动范围执行对应操作。

### 3.1 拉取代码

```bash
cd /home/jiahao/ai-agent/ai-agent
git pull
```

### 3.2 判断需要做什么

| 改动范围 | 需要的操作 |
| --- | --- |
| 只改了后端 Python 代码 | 重启后端 |
| 只改了前端 React 代码 | 重新构建前端 |
| 前后端都改了 | 重启后端 + 重新构建前端 |
| `requirements.txt` 变了 | 重装后端依赖 + 重启后端 |
| `package.json` 变了 | 重装前端依赖 + 重新构建前端 |

### 3.3 重启后端

```bash
sudo systemctl restart rag-api
sudo systemctl status rag-api
```

如果 `requirements.txt` 有变化：

```bash
cd /home/jiahao/ai-agent/ai-agent/rag-chat-platform/backend
source .venv/bin/activate
pip install -r requirements.txt
deactivate
sudo systemctl restart rag-api
```

### 3.4 重新构建前端

```bash
cd /home/jiahao/ai-agent/ai-agent/rag-chat-platform/frontend
npm install          # package.json 没变可跳过
npm run build
```

Nginx 是静态文件托管，构建完即生效。用户端可能需要强制刷新（Ctrl+F5）清缓存。

### 3.5 验证

```bash
# 后端
curl -s http://127.0.0.1:8000/api/health

# 前端
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:90
```

浏览器访问 `http://服务器IP:90`，确认页面正常。

---

## 四、数据与备份

### 4.1 不要删的数据目录

以下都在 `backend/` 目录下，**重启、更新、重新部署都不会动它们**，但手动删除会丢数据：

| 路径 | 内容 |
| --- | --- |
| `backend/app.db` | 用户、对话、文档元数据 |
| `backend/chroma_db/` | 向量索引 |
| `backend/knowledge_base/` | 原始文档 |
| `backend/models/` | embedding 模型（约 2GB） |

### 4.2 备份

```bash
cd /home/jiahao/ai-agent/ai-agent/rag-chat-platform/backend
tar -czf ~/rag-backup-$(date +%Y%m%d).tar.gz app.db chroma_db knowledge_base
```

恢复时解压回去即可。`models/` 目录不用备份，删了会自动重新下载。

### 4.3 数据库迁移

本项目用 SQLite，schema 变更会在启动时自动执行（加列、加索引），不需要手动迁移。如果 `app.db` 文件损坏，删掉重启会自动新建，但数据会丢——所以定期备份很重要。

---

## 五、环境变量

可在 systemd 服务文件里通过 `Environment=` 设置，或写一个 `.env` 文件用 `EnvironmentFile=` 加载。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `JWT_SECRET` | 默认值（生产必须改） | JWT 签名密钥 |
| `HF_ENDPOINT` | `https://huggingface.co` | 国内建议设为 `https://hf-mirror.com` |
| `HF_HUB_DISABLE_XET` | 未设置 | 建议设为 `1`，避免大文件下载卡住 |
| `CHROMA_PERSIST_DIR` | `backend/chroma_db` | 向量库持久化目录 |
| `KNOWLEDGE_BASE_DIR` | `backend/knowledge_base` | 原始文档目录 |
| `SQLITE_PATH` | `backend/app.db` | 数据库路径 |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | embedding 模型 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API 地址 |
| `DEFAULT_MODEL` | `deepseek-flash` | 默认对话模型 |
| `RECENT_CONTEXT_TURNS` | `2` | 保留最近几轮原文 |
| `SUMMARY_TRIGGER_TOKENS` | `800` | 触发摘要的 token 阈值 |
| `SUMMARY_TRIGGER_TURNS` | `2` | 触发摘要的轮数阈值 |

改完环境变量后要重启后端：

```bash
sudo systemctl restart rag-api
```

---

## 六、常用运维命令

```bash
# 查看后端状态
sudo systemctl status rag-api

# 查看后端实时日志
sudo journalctl -u rag-api -f

# 查看后端最近 100 行日志
sudo journalctl -u rag-api -n 100

# 重启后端
sudo systemctl restart rag-api

# 停止 / 启动后端
sudo systemctl stop rag-api
sudo systemctl start rag-api

# 测试 Nginx 配置
sudo nginx -t

# 重载 Nginx
sudo systemctl reload nginx

# 查看 Nginx 错误日志
sudo tail -f /var/log/nginx/error.log
```

---

## 七、常见问题

### 7.1 页面打不开（502 Bad Gateway）

后端没起来或端口不对。

```bash
sudo systemctl status rag-api
curl -s http://127.0.0.1:8000/api/health
```

如果后端挂了，看日志找原因：

```bash
sudo journalctl -u rag-api -n 50
```

常见原因：`JWT_SECRET` 没设、Python 依赖没装全、虚拟环境路径不对。

### 7.2 上传文件失败（413 Request Entity Too Large）

Nginx 默认限制 1MB。在站点配置的 `server` 块里加：

```nginx
client_max_body_size 50m;
```

然后 `sudo systemctl reload nginx`。

### 7.3 首次索引很慢 / 模型下载卡住

确认 `HF_ENDPOINT=https://hf-mirror.com` 和 `HF_HUB_DISABLE_XET=1` 已设置。模型约 2GB，下载到 `backend/models/`。下载完后续启动不用再下。

### 7.4 前端能打开但接口报错

检查 Nginx 的 `/api/` 反代是否指向 `127.0.0.1:8000`，以及后端是否在跑。

### 7.5 对话历史丢失

`app.db` 被删或路径变了。确认 `SQLITE_PATH` 没被改，且 `app.db` 文件还在。

### 7.6 忘记 admin 密码

直接删 `app.db` 重启会重建默认账号，但会丢所有数据。更稳妥的做法是临时写脚本改密码，或提前在用户管理页面改掉默认密码。

---

## 八、更新流程速查

```bash
# 1. 拉代码
cd /home/jiahao/ai-agent/ai-agent
git pull

# 2. 后端（看 requirements.txt 是否变化）
cd rag-chat-platform/backend
source .venv/bin/activate
pip install -r requirements.txt    # 没变可跳过
deactivate
sudo systemctl restart rag-api

# 3. 前端（看 package.json 是否变化）
cd ../frontend
npm install                        # 没变可跳过
npm run build

# 4. 验证
curl -s http://127.0.0.1:8000/api/health
```
