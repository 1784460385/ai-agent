import os
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import CHUNK_OVERLAP, CHUNK_SIZE, KNOWLEDGE_BASE_DIR

TEXT_SUFFIXES = {".txt", ".md", ".markdown"}


def _load_text(path: Path):
    last_error: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return TextLoader(str(path), encoding=encoding).load()
        except Exception as exc:
            last_error = exc
    raise RuntimeError(last_error or f"无法读取 {path.name}")


def load_and_split_documents():
    """加载知识库目录下所有文档并分块。"""
    os.makedirs(KNOWLEDGE_BASE_DIR, exist_ok=True)
    all_docs = []
    root = Path(KNOWLEDGE_BASE_DIR)

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        suffix = path.suffix.lower()
        try:
            if suffix == ".pdf":
                all_docs.extend(PyPDFLoader(str(path)).load())
            elif suffix in TEXT_SUFFIXES:
                all_docs.extend(_load_text(path))
        except Exception as exc:
            print(f"[WARN] 加载 {path.name} 失败: {exc}")

    if not all_docs:
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "！", "？", " ", ""],
        length_function=len,
    )
    return splitter.split_documents(all_docs)


def _source_label(metadata: dict) -> str:
    source = Path(str(metadata.get("source") or "未知文件")).name
    page = metadata.get("page")
    if page is None:
        return source
    try:
        return f"{source} 第{int(page) + 1}页"
    except (TypeError, ValueError):
        return source


def index_knowledge_base():
    """执行完整的索引流程：加载 → 分块 → 向量化 → 存储。"""
    from vector_store import replace_documents

    chunks = load_and_split_documents()
    if not chunks:
        return {"status": "empty", "message": "知识库目录为空或无支持的文档"}

    texts: list[str] = []
    ids: list[str] = []
    metadatas: list[dict] = []
    for chunk in chunks:
        content = chunk.page_content.strip()
        if not content:
            continue
        texts.append(content)
        ids.append(f"chunk_{len(ids)}")
        metadatas.append({"source": _source_label(chunk.metadata), "chunk": len(ids) - 1})

    if not texts:
        return {"status": "empty", "message": "文档中没有可索引的文本"}

    count = replace_documents(texts, ids, metadatas)
    return {"status": "ok", "chunks_indexed": count}


def build_rag_prompt(user_question: str, retrieved_docs: list[str]) -> str:
    """构建增强 Prompt。"""
    context = "\n\n---\n\n".join(retrieved_docs) if retrieved_docs else "（知识库中没有检索到相关内容）"
    return f"""你是一个知识库助手。请严格根据以下提供的上下文信息来回答用户问题。

规则：
1. 仅使用上下文中明确出现的信息作答。
2. 如果上下文信息不足以回答问题，请如实告知用户"根据现有知识库，我无法回答这个问题"。
3. 回答时请标注信息来源（如果上下文中包含来源标识）。

## 上下文信息
{context}

## 用户问题
{user_question}"""
