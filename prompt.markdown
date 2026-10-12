1. 项目概述
构建一个全栈 Web 应用，具备以下核心能力：

知识库索引：将本地文档（PDF/Markdown/TXT）通过 Embedding 向量化后存入 Chroma 向量数据库。

RAG 检索问答：用户提问时，从知识库检索最相关的文本片段，拼接进 Prompt 后交给 DeepSeek 生成回答。

用户自备 API Key：前端提供 API Key 输入框，Key 随请求透传给后端，后端不存储任何用户凭证。

流式响应：后端通过 SSE（Server-Sent Events）向前端推送 DeepSeek 的流式输出。

架构流向：
用户提问 → React 前端 (携带 API Key)
  → FastAPI 后端 /api/chat
    → Chroma 向量检索 (取 Top-K 相关片段)
    → 构建增强 Prompt (System Prompt + 检索上下文 + 用户问题)
    → DeepSeek API (使用用户提供的 Key)
  → SSE 流式返回 → React 前端逐字渲染

2. 项目目录结构
rag-chat-platform/
├── backend/
│   ├── main.py                  # FastAPI 入口，路由定义
│   ├── rag_engine.py            # RAG 核心逻辑（文档加载、分块、检索）
│   ├── vector_store.py          # Chroma 向量库管理
│   ├── models.py                # Pydantic 请求/响应模型
│   ├── config.py                # 配置常量
│   ├── knowledge_base/          # 原始知识库文件存放目录
│   │   ├── *.pdf
│   │   ├── *.md
│   │   └── *.txt
│   ├── chroma_db/               # Chroma 持久化数据（自动生成）
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ChatWindow.tsx    # 对话主窗口
│   │   │   ├── MessageBubble.tsx # 单条消息渲染
│   │   │   ├── ApiKeyPanel.tsx   # API Key 设置面板
│   │   │   └── KnowledgeUpload.tsx # 知识库上传
│   │   ├── hooks/
│   │   │   └── useChat.ts        # 聊天逻辑与 SSE 解析
│   │   └── api/
│   │       └── client.ts         # 后端 API 调用封装
│   ├── package.json
│   └── vite.config.ts
└── README.md

3. 依赖与版本
fastapi>=0.115.0
uvicorn>=0.29.0
langchain>=0.3.0
langchain-community>=0.3.0
langchain-chroma>=0.2.0
langchain-openai>=0.3.0
chromadb>=0.5.0
sentence-transformers>=3.0.0
pypdf>=4.0.0
python-multipart>=0.0.9

Python 版本要求：>=3.12

前端 (package.json 关键依赖)
{
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "@assistant-ui/react": "^0.9.0",
    "eventsource-parser": "^3.0.0"
  }
}

前端聊天 UI 推荐使用 @assistant-ui/react，它开箱即用地处理流式响应、自动滚动和实时更新

4. 后端实现规范
4.1 配置模块 — config.py
# config.py
CHROMA_PERSIST_DIR = "./chroma_db"
KNOWLEDGE_BASE_DIR = "./knowledge_base"
COLLECTION_NAME = "knowledge_base"
EMBEDDING_MODEL = "BAAI/bge-m3"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
RETRIEVAL_TOP_K = 3
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"

设计决策：

CHUNK_SIZE=500、CHUNK_OVERLAP=50：兼顾语义完整性和检索粒度。重叠部分防止关键信息在切分处丢失。

EMBEDDING_MODEL="BAAI/bge-m3"：中文语义理解能力强，支持多语言，本地运行无需外部 API。

RETRIEVAL_TOP_K=3：返回最相关的 3 个文本块，平衡上下文长度和信息量。

4.2 向量库管理 — vector_store.py
# vector_store.py
import chromadb
from chromadb.utils import embedding_functions
from config import CHROMA_PERSIST_DIR, COLLECTION_NAME, EMBEDDING_MODEL

def get_chroma_client():
    """创建 Chroma 持久化客户端"""
    return chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

def get_embedding_function():
    """加载 Embedding 模型"""
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )

def get_or_create_collection():
    """获取或创建知识库集合"""
    client = get_chroma_client()
    ef = get_embedding_function()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef
    )

def add_documents(texts: list[str], ids: list[str]):
    """将文本块存入向量库"""
    collection = get_or_create_collection()
    collection.add(documents=texts, ids=ids)
    return len(texts)

def query_documents(query_text: str, n_results: int = 3):
    """检索最相关的文本块"""
    collection = get_or_create_collection()
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results
    )
    return results['documents'][0]  # list[str]

注意事项：

PersistentClient 将向量数据持久化到磁盘，重启后无需重新索引。

SentenceTransformerEmbeddingFunction 首次调用时会自动下载模型，请确保网络可达 HuggingFace。

如果模型下载超时，可提前手动下载到本地并在 EMBEDDING_MODEL 中指定本地路径。

4.3 RAG 引擎 — rag_engine.py
# rag_engine.py
import os
from langchain_community.document_loaders import (
    PyPDFLoader, TextLoader, DirectoryLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from config import KNOWLEDGE_BASE_DIR, CHUNK_SIZE, CHUNK_OVERLAP

def load_and_split_documents():
    """加载知识库目录下所有文档并分块"""
    all_docs = []

    # 按文件类型分别加载
    for ext, loader_cls in [("**/*.pdf", PyPDFLoader), ("**/*.txt", TextLoader)]:
        try:
            loader = DirectoryLoader(
                KNOWLEDGE_BASE_DIR, glob=ext, loader_cls=loader_cls
            )
            all_docs.extend(loader.load())
        except Exception as e:
            print(f"[WARN] 加载 {ext} 文件失败: {e}")

    if not all_docs:
        return []

    # 递归分块
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "！", "？", " ", ""],
        length_function=len
    )
    chunks = splitter.split_documents(all_docs)
    return chunks

def index_knowledge_base():
    """执行完整的索引流程：加载 → 分块 → 向量化 → 存储"""
    from vector_store import add_documents
    chunks = load_and_split_documents()
    if not chunks:
        return {"status": "empty", "message": "知识库目录为空或无支持的文档"}

    texts = [c.page_content for c in chunks]
    ids = [f"chunk_{i}" for i in range(len(texts))]
    count = add_documents(texts, ids)
    return {"status": "ok", "chunks_indexed": count}

def build_rag_prompt(user_question: str, retrieved_docs: list[str]) -> str:
    """构建增强 Prompt"""
    context = "\n\n---\n\n".join(retrieved_docs)
    return f"""你是一个知识库助手。请严格根据以下提供的上下文信息来回答用户问题。

规则：
1. 仅使用上下文中明确出现的信息作答。
2. 如果上下文信息不足以回答问题，请如实告知用户"根据现有知识库，我无法回答这个问题"。
3. 回答时请标注信息来源（如果上下文中包含来源标识）。

## 上下文信息
{context}

## 用户问题
{user_question}"""

关键设计点：

使用 RecursiveCharacterTextSplitter 按段落、句子层级递归切分，优先在语义边界处断开。

分隔符列表包含中文标点（。！？），确保中文文档的切分质量。

Prompt 中明确指示模型基于上下文回答，这是减少幻觉的核心手段。

4.4 Pydantic 模型 — models.py
# models.py
from pydantic import BaseModel, Field
from typing import Optional

class ModelConfig(BaseModel):
    api_key: str = Field(..., description="用户提供的 DeepSeek API Key")
    base_url: str = Field(default="https://api.deepseek.com")
    model_name: str = Field(default="deepseek-flash")

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    config: ModelConfig

class IndexResponse(BaseModel):
    status: str
    chunks_indexed: Optional[int] = None
    message: Optional[str] = None

4.5 FastAPI 入口 — main.py
# main.py
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
import os, shutil

from models import ChatRequest, IndexResponse
from rag_engine import index_knowledge_base, build_rag_prompt
from vector_store import query_documents
from config import KNOWLEDGE_BASE_DIR, RETRIEVAL_TOP_K

app = FastAPI(title="RAG Knowledge Base Chat API")

# CORS 配置：允许前端开发服务器访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite 默认端口
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """RAG 问答接口：检索 → 增强 → 流式生成"""

    # Step 1: 从知识库检索相关片段
    retrieved_docs = query_documents(
        request.message, n_results=RETRIEVAL_TOP_K
    )

    # Step 2: 构建增强 Prompt
    system_prompt = build_rag_prompt(request.message, retrieved_docs)

    # Step 3: 使用用户提供的 API Key 动态创建 DeepSeek 客户端
    client = OpenAI(
        api_key=request.config.api_key,
        base_url=request.config.base_url
    )

    # Step 4: 流式调用 DeepSeek
    stream = client.chat.completions.create(
        model=request.config.model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.message}
        ],
        stream=True,
        temperature=0.3
    )

    # Step 5: SSE 流式返回
    async def event_stream():
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield f"data: {delta.content}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream"
    )

@app.post("/api/index", response_model=IndexResponse)
async def index_endpoint():
    """触发知识库重新索引"""
    result = index_knowledge_base()
    return IndexResponse(**result)

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    """上传文档到知识库目录"""
    os.makedirs(KNOWLEDGE_BASE_DIR, exist_ok=True)
    file_path = os.path.join(KNOWLEDGE_BASE_DIR, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"status": "ok", "filename": file.filename}

API Key 安全策略：用户的 API Key 仅存在于请求生命周期内，后端不写入日志、不存入数据库、不缓存。每次请求动态创建 OpenAI 客户端，请求结束后客户端被垃圾回收。

DeepSeek 兼容性说明：DeepSeek API 使用与 OpenAI 完全兼容的接口格式，只需设置 base_url="https://api.deepseek.com" 即可直接使用 OpenAI SDK 调用。可用模型包括 deepseek-flash 和 deepseek-v4-pro。

5. Harness 集成层
5.1 推荐方案：llm-harness 直接编排
在你的场景中，最直接的 Harness 集成方式是使用 llm-harness 作为 Agent 执行底座，将 RAG 检索封装为一个工具，让 Agent 自主决定何时调用知识库检索。
pip install llm-harness[openai]
# agent_service.py — Harness Agent 封装
import os, asyncio
from pathlib import Path
from llm_harness.adapters.providers.openai_compat_provider import OpenAICompatProvider
from llm_harness.adapters.sandbox.srt import SRTSandboxBackend
from llm_harness.core.harness import Harness
from llm_harness.core.session.session import Session
from llm_harness.core.bus.events import InboundMessage
from llm_harness.core.tools.base import ToolRegistry
from llm_harness.core.tools.factory import ToolFactory

async def create_rag_agent(user_api_key: str):
    """创建一个带有知识库检索能力的 Agent"""

    # 1. 配置 LLM Provider（使用用户的 API Key）
    provider = OpenAICompatProvider(
        api_key=user_api_key,
        api_base="https://api.deepseek.com",
    )

    # 2. 配置沙箱（Agent 的文件操作范围）
    sandbox = SRTSandboxBackend(Path("./workspace"))

    # 3. 注册工具
    factory = ToolFactory(sandbox=sandbox)
    tools = ToolRegistry()
    for name in ["read_file", "write_file", "web_search"]:
        tool = factory.build(name)
        if tool:
            tools.register(tool)

    # 4. 创建 Harness 实例
    harness = Harness(
        provider=provider,
        model="deepseek-chat",
        tools=tools,
        sandbox=sandbox
    )
    agent = harness.create_agent()
    return agent, harness

llm-harness 是一个纯异步、依赖注入的 Agent 引擎内核，所有组件（Provider、Sandbox、Memory、Session）均通过 Protocol 驱动，无需继承即可替换。它内置 15 个工具和 20+ LLM 服务商适配，支持 OpenAI、DeepSeek 等。

5.2 将 RAG 检索注册为 Harness 工具
在 Harness 中，工具是模型可调用的函数。将知识库检索注册为工具，可以让 Agent 自主判断是否需要查知识库：
# rag_tool.py — 将 RAG 检索封装为 Harness 工具
from llm_harness.core.tools.base import Tool

class KnowledgeBaseSearchTool(Tool):
    name = "search_knowledge_base"
    description = "搜索本地知识库，获取与用户问题最相关的文档片段。在回答任何与知识库内容相关的问题前，应先调用此工具。"

    def __init__(self, vector_store_query_fn):
        self._query_fn = vector_store_query_fn

    async def execute(self, query: str, top_k: int = 3) -> str:
        """执行知识库检索，返回拼接后的上下文文本"""
        docs = self._query_fn(query, n_results=top_k)
        if not docs:
            return "知识库中未找到相关内容。"
        return "\n\n---\n\n".join(docs)

    def schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询"},
                    "top_k": {"type": "integer", "default": 3, "description": "返回结果数量"}
                },
                "required": ["query"]
            }
        }

6. 前端实现规范
6.1 API Key 设置面板 — ApiKeyPanel.tsx
// components/ApiKeyPanel.tsx
import { useState } from 'react';

interface Props {
  onSave: (key: string) => void;
}

export function ApiKeyPanel({ onSave }: Props) {
  const [key, setKey] = useState('');
  const [visible, setVisible] = useState(false);

  const handleSave = () => {
    if (!key.startsWith('sk-')) {
      alert('API Key 格式不正确，应以 sk- 开头');
      return;
    }
    onSave(key);
    setVisible(false);
  };

  return (
    <div className="p-4 border rounded-lg bg-gray-50">
      <label className="block text-sm font-medium mb-2">
        DeepSeek API Key
      </label>
      <input
        type="password"
        value={key}
        onChange={(e) => setKey(e.target.value)}
        placeholder="sk-xxxxxxxxxxxxxxxx"
        className="w-full p-2 border rounded"
      />
      <button
        onClick={handleSave}
        className="mt-2 px-4 py-1 bg-blue-600 text-white rounded"
      >
        保存
      </button>
    </div>
  );
}
安全约定：API Key 仅保存在前端状态（React state 或 sessionStorage）中，不写入 localStorage（防止 XSS 持久化泄露），页面刷新后需重新输入。
6.2 聊天 Hook — useChat.ts
// hooks/useChat.ts
import { useState, useCallback, useRef } from 'react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export function useChat(apiKey: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (text: string) => {
    if (!apiKey) throw new Error('请先设置 API Key');

    setMessages(prev => [...prev, { role: 'user', content: text }]);
    setIsLoading(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          config: {
            api_key: apiKey,
            base_url: 'https://api.deepseek.com',
            model_name: 'deepseek-flash'
          }
        }),
        signal: controller.signal
      });

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let assistantContent = '';

      setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

      while (reader) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') continue;
            assistantContent += data;
            setMessages(prev => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                role: 'assistant',
                content: assistantContent
              };
              return updated;
            });
          }
        }
      }
    } finally {
      setIsLoading(false);
      abortRef.current = null;
    }
  }, [apiKey]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { messages, isLoading, sendMessage, stop };
}
6.3 推荐组件库
如果希望快速获得生产级的聊天体验，推荐使用 @assistant-ui/react。它是一个开源的 TypeScript/React 库，内置处理流式响应、自动滚动、无障碍访问和实时更新，开箱即用。其核心优势在于：

完整的 runtime 层（线程管理、消息分支、附件处理）

与 useStream 通过 useExternalStoreRuntime 适配器连接

支持消息分支、重试、自动滚动等生产级 UX

对于本项目的自定义需求（API Key 透传），建议在 @assistant-ui/react 的 runtime 适配层中注入 API Key 逻辑。
7. 部署与运行
7.1 后端启动
bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
首次启动时会自动下载 Embedding 模型（约 1-2 GB），请确保磁盘空间充足。

7.2 前端启动
bash
cd frontend
npm install
npm run dev
前端默认运行在 http://localhost:5173，需要在 vite.config.ts 中配置代理或确保后端 CORS 已允许该来源。
7.3 知识库索引流程
将 PDF/Markdown/TXT 文件放入 backend/knowledge_base/ 目录。

调用 POST /api/index 触发索引（或在前端点击“重建索引”按钮）。

索引完成后，Chroma 数据持久化在 backend/chroma_db/ 目录。

之后每次 /api/chat 请求都会自动从该向量库检索。
8. 环境变量参考
变量名	默认值	说明
CHROMA_PERSIST_DIR	./chroma_db	Chroma 持久化目录
KNOWLEDGE_BASE_DIR	./knowledge_base	原始文档存放目录
EMBEDDING_MODEL	BAAI/bge-m3	Embedding 模型名称
CHUNK_SIZE	500	文本块大小（字符数）
CHUNK_OVERLAP	50	文本块重叠大小
RETRIEVAL_TOP_K	3	检索返回的文本块数量
DEEPSEEK_BASE_URL	https://api.deepseek.com	DeepSeek API 地址
DEFAULT_MODEL	deepseek-flash	默认模型名称
9. 验证标准
Agent 完成开发后，使用以下标准验证：

索引验证：向 knowledge_base/ 放入 3 个测试文档，调用 POST /api/index，确认返回 chunks_indexed > 0。

检索验证：调用 POST /api/chat，发送一个知识库中有答案的问题，确认返回内容与文档一致。

拒答验证：发送一个知识库中不存在的问题，确认模型回复“根据现有知识库，我无法回答这个问题”而非幻觉编造。

API Key 透传验证：使用无效 API Key 发送请求，确认返回 401 错误而非使用服务端 Key。

流式响应验证：在前端观察 AI 回复是否逐字显示，而非一次性返回全文。
