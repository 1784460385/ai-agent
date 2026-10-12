import os
import threading

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import chromadb
from chromadb.utils import embedding_functions

from config import CHROMA_PERSIST_DIR, COLLECTION_NAME, EMBEDDING_MODEL
from folders import folder_map, list_folders

_lock = threading.Lock()
_model_lock = threading.Lock()
_client: chromadb.PersistentClient | None = None
_embedding_function = None


def collection_name(folder_key: str) -> str:
    folder = folder_map().get(folder_key)
    if folder:
        return folder["collection"]
    return f"kb_{folder_key}"


def get_chroma_client() -> chromadb.PersistentClient:
    """创建 Chroma 持久化客户端。"""
    global _client
    if _client is None:
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return _client


def get_embedding_function():
    """加载 Embedding 模型。首次调用会使用 backend/models 里的本地模型。"""
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


def get_collection(dept: str):
    """获取指定部门的 Collection。"""
    return get_chroma_client().get_or_create_collection(
        name=collection_name(dept),
        embedding_function=get_embedding_function(),
    )


def department_count(dept: str) -> int:
    """返回部门片段数。不存在时为 0，且不加载 Embedding 模型。"""
    try:
        return get_chroma_client().get_collection(collection_name(dept)).count()
    except Exception:
        return 0


def collection_count() -> int:
    """返回全部文件夹的片段总数。"""
    return sum(department_count(folder["key"]) for folder in list_folders())


def _write(dept: str, texts: list[str], ids: list[str], metadatas: list[dict] | None) -> None:
    collection = get_collection(dept)
    batch_size = 128
    for start in range(0, len(texts), batch_size):
        end = start + batch_size
        collection.add(
            documents=texts[start:end],
            ids=ids[start:end],
            metadatas=None if metadatas is None else metadatas[start:end],
        )


def replace_documents(
    dept: str,
    texts: list[str],
    ids: list[str],
    metadatas: list[dict] | None = None,
) -> int:
    """清空该部门后重建索引。"""
    if texts:
        get_embedding_function()
    with _lock:
        client = get_chroma_client()
        try:
            client.delete_collection(collection_name(dept))
        except Exception:
            pass
        if texts:
            _write(dept, texts, ids, metadatas)
    return len(texts)


def delete_folder_collection(folder_key: str) -> None:
    try:
        get_chroma_client().delete_collection(collection_name(folder_key))
    except Exception:
        pass


def delete_legacy_collection() -> None:
    try:
        get_chroma_client().delete_collection(COLLECTION_NAME)
    except Exception:
        pass


def _hits_from_result(dept: str, results: dict) -> list[dict]:
    documents = (results.get("documents") or [[]])[0] or []
    metadatas = (results.get("metadatas") or [[]])[0] or []
    distances = (results.get("distances") or [[]])[0] or []
    folder = folder_map().get(dept) or {}
    dept_name = folder.get("name", dept)
    hits: list[dict] = []
    for index, content in enumerate(documents):
        if not content:
            continue
        meta = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
        hits.append(
            {
                "content": content,
                "source": meta.get("source") or "未知来源",
                "department": dept,
                "department_name": dept_name,
                "distance": distances[index] if index < len(distances) else None,
            }
        )
    return hits


def search_departments(departments: list[str], query_text: str, n_results: int = 3) -> list[dict]:
    """从指定部门检索，每个部门最多返回 n_results 条。"""
    with _lock:
        client = get_chroma_client()
        pending: list[tuple[str, int]] = []
        for dept in departments:
            if dept not in folder_map():
                continue
            try:
                count = client.get_collection(collection_name(dept)).count()
            except Exception:
                continue
            if count:
                pending.append((dept, count))
        if not pending:
            return []

        hits: list[dict] = []
        for dept, count in pending:
            collection = get_collection(dept)
            results = collection.query(
                query_texts=[query_text],
                n_results=min(n_results, count),
                include=["documents", "metadatas", "distances"],
            )
            hits.extend(_hits_from_result(dept, results))
        return hits


def query_documents(dept: str, query_text: str, n_results: int = 3) -> list[str]:
    """从指定部门检索文本。"""
    return [hit["content"] for hit in search_departments([dept], query_text, n_results)]


def query_multiple_departments(departments: list[str], query_text: str, n_results: int = 3) -> list[str]:
    """从多个部门检索并合并。"""
    return [hit["content"] for hit in search_departments(departments, query_text, n_results)]
