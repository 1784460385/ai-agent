import os
import threading

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# Windows 上 Xet 大文件下载容易停在 0 字节，改走普通 HTTP。
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import chromadb
from chromadb.utils import embedding_functions

from config import CHROMA_PERSIST_DIR, COLLECTION_NAME, EMBEDDING_MODEL

_lock = threading.Lock()
_model_lock = threading.Lock()
_client: chromadb.PersistentClient | None = None
_embedding_function = None


def get_chroma_client() -> chromadb.PersistentClient:
    """创建 Chroma 持久化客户端。"""
    global _client
    if _client is None:
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return _client


def get_embedding_function():
    """加载 Embedding 模型。首次调用会把模型下载到 backend/models。"""
    global _embedding_function
    if _embedding_function is not None:
        return _embedding_function
    with _model_lock:
        if _embedding_function is None:
            from model_download import ensure_local_model

            local_model = ensure_local_model(EMBEDDING_MODEL)
            _embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=local_model
            )
    return _embedding_function


def get_or_create_collection():
    """获取或创建知识库集合。"""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=get_embedding_function(),
    )


def collection_count() -> int:
    """返回已索引片段数。集合不存在时返回 0，且不加载 Embedding 模型。"""
    client = get_chroma_client()
    try:
        return client.get_collection(COLLECTION_NAME).count()
    except Exception:
        return 0


def reset_collection():
    """重建索引用：删掉旧集合，避免重复 id。"""
    client = get_chroma_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    return get_or_create_collection()


def _add(texts: list[str], ids: list[str], metadatas: list[dict] | None) -> None:
    collection = get_or_create_collection()
    batch_size = 128
    for start in range(0, len(texts), batch_size):
        end = start + batch_size
        collection.add(
            documents=texts[start:end],
            ids=ids[start:end],
            metadatas=None if metadatas is None else metadatas[start:end],
        )


def add_documents(
    texts: list[str],
    ids: list[str],
    metadatas: list[dict] | None = None,
) -> int:
    """将文本块存入向量库。"""
    if not texts:
        return 0
    with _lock:
        _add(texts, ids, metadatas)
    return len(texts)


def replace_documents(
    texts: list[str],
    ids: list[str],
    metadatas: list[dict] | None = None,
) -> int:
    """清空后重建索引，避免重复 id，并与检索互斥。"""
    if not texts:
        return 0
    get_embedding_function()
    with _lock:
        client = get_chroma_client()
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        _add(texts, ids, metadatas)
    return len(texts)


def search(query_text: str, n_results: int = 3) -> list[dict]:
    """检索最相关的文本块，附带来源元数据。"""
    with _lock:
        client = get_chroma_client()
        try:
            existing = client.get_collection(COLLECTION_NAME)
        except Exception:
            return []
        count = existing.count()
        if count == 0:
            return []

        collection = get_or_create_collection()
        results = collection.query(
            query_texts=[query_text],
            n_results=min(n_results, count),
            include=["documents", "metadatas", "distances"],
        )

    documents = (results.get("documents") or [[]])[0] or []
    metadatas = (results.get("metadatas") or [[]])[0] or []
    distances = (results.get("distances") or [[]])[0] or []

    hits: list[dict] = []
    for index, content in enumerate(documents):
        if not content:
            continue
        meta = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
        hits.append(
            {
                "content": content,
                "source": meta.get("source") or "未知来源",
                "distance": distances[index] if index < len(distances) else None,
            }
        )
    return hits


def query_documents(query_text: str, n_results: int = 3) -> list[str]:
    """检索最相关的文本块。"""
    return [hit["content"] for hit in search(query_text, n_results=n_results)]
