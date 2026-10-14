from __future__ import annotations

import os
import threading
import time

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import chromadb
from chromadb.utils import embedding_functions

from config import (
    CHROMA_PERSIST_DIR,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    MAX_CONTEXT_CHUNKS,
    NEIGHBOR_EXPAND,
    RECALL_K,
    RERANK_CANDIDATES,
    RETRIEVAL_TOP_K,
    SEARCH_ALL_FOLDERS,
    UNROUTED_FOLDER_WEIGHT,
)
from devices import model_device
from database import fts_search_chunks, get_knowledge_chunks_by_ids
from folders import folder_map, list_folders
from reranker import get_reranker, rerank, reranker_enabled, reranker_status

_lock = threading.Lock()
_model_lock = threading.Lock()
_client: chromadb.PersistentClient | None = None
_embedding_function = None
RRF_K = 60


def collection_name(user_id: int, folder_key: str) -> str:
    folder = folder_map(user_id).get(folder_key)
    if folder:
        return folder["collection"]
    return f"u{user_id}_kb_{folder_key}"


def get_chroma_client() -> chromadb.PersistentClient:
    """创建 Chroma 持久化客户端。"""
    global _client
    if _client is None:
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return _client


def get_embedding_function():
    """加载 Embedding 模型。首次调用会使用 backend/models 里的本地模型，有 GPU 时用 GPU 半精度。"""
    global _embedding_function
    if _embedding_function is not None:
        return _embedding_function
    with _model_lock:
        if _embedding_function is None:
            import torch
            from sentence_transformers import SentenceTransformer

            from devices import empty_cuda_cache
            from model_download import ensure_local_model

            local_model = ensure_local_model(EMBEDDING_MODEL)
            device = model_device()
            # Chroma 的 EmbeddingFunction 不允许传入 torch.dtype，先自行以 fp16 加载再注入缓存
            if device.startswith("cuda"):
                st = SentenceTransformer(
                    local_model,
                    device=device,
                    model_kwargs={"torch_dtype": torch.float16},
                )
                st.half()
                embedding_functions.SentenceTransformerEmbeddingFunction.models[local_model] = st
                empty_cuda_cache()
            function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=local_model,
                device=device,
            )
            if device.startswith("cuda"):
                used = torch.cuda.memory_allocated(0) / 1024 / 1024
                print(f"[EMBED] 已加载 {EMBEDDING_MODEL} ({device}, {used:.0f} MiB)", flush=True)
            else:
                print(f"[EMBED] 已加载 {EMBEDDING_MODEL} ({device})", flush=True)
            _embedding_function = function
    return _embedding_function


def warmup_models() -> None:
    """后台预加载本地模型，避免第一次提问时才加载。"""
    try:
        get_embedding_function()
        if not reranker_enabled():
            print("[RERANK] 已禁用（环境变量 RERANKER_ENABLED=0）。删除该变量后重启即可启用。", flush=True)
            return
        get_reranker()
        print(f"[RERANK] 状态: {reranker_status()}", flush=True)
    except Exception as exc:
        print(f"[WARN] 模型预加载失败: {exc}", flush=True)


def get_collection(user_id: int, dept: str):
    """获取指定用户某个文件夹的 Collection。"""
    return get_chroma_client().get_or_create_collection(
        name=collection_name(user_id, dept),
        embedding_function=get_embedding_function(),
    )


def department_count(user_id: int, dept: str) -> int:
    """返回部门片段数。不存在时为 0，且不加载 Embedding 模型。"""
    try:
        return get_chroma_client().get_collection(collection_name(user_id, dept)).count()
    except Exception:
        return 0


def collection_count(user_id: int) -> int:
    """返回该用户全部文件夹的片段总数。"""
    return sum(department_count(user_id, folder["key"]) for folder in list_folders(user_id))


def delete_collection_by_name(name: str) -> None:
    try:
        get_chroma_client().delete_collection(name)
    except Exception:
        pass


def _write(user_id: int, dept: str, texts: list[str], ids: list[str], metadatas: list[dict] | None) -> None:
    collection = get_collection(user_id, dept)
    batch_size = 128
    for start in range(0, len(texts), batch_size):
        end = start + batch_size
        collection.add(
            documents=texts[start:end],
            ids=ids[start:end],
            metadatas=None if metadatas is None else metadatas[start:end],
        )


def replace_documents(
    user_id: int,
    dept: str,
    texts: list[str],
    ids: list[str],
    metadatas: list[dict] | None = None,
) -> int:
    """清空该部门后重建向量索引。"""
    if texts:
        get_embedding_function()
    with _lock:
        name = collection_name(user_id, dept)
        client = get_chroma_client()
        try:
            client.delete_collection(name)
        except Exception:
            pass
        if texts:
            _write(user_id, dept, texts, ids, metadatas)
    return len(texts)


def delete_folder_collection(user_id: int, folder_key: str) -> None:
    delete_collection_by_name(collection_name(user_id, folder_key))


def delete_legacy_collection() -> None:
    try:
        get_chroma_client().delete_collection(COLLECTION_NAME)
    except Exception:
        pass


def _make_hit(dept: str, dept_name: str, chunk_id: str, content: str, meta: dict | None, distance=None) -> dict:
    meta = meta or {}
    return {
        "id": f"{dept}:{chunk_id}",
        "content": content,
        "source": meta.get("source") or "未知来源",
        "department": dept,
        "department_name": dept_name,
        "distance": distance,
    }


def _vector_hits(dept: str, dept_name: str, results: dict, query_index: int) -> list[dict]:
    ids = (results.get("ids") or [])[query_index] or []
    documents = (results.get("documents") or [])[query_index] or []
    metadatas = (results.get("metadatas") or [])[query_index] or []
    distances = (results.get("distances") or [])[query_index] or []
    hits: list[dict] = []
    for index, content in enumerate(documents):
        if not content:
            continue
        meta = metadatas[index] if index < len(metadatas) else None
        distance = distances[index] if index < len(distances) else None
        hits.append(_make_hit(dept, dept_name, ids[index], content, meta, distance))
    return hits


def _keyword_hits(user_id: int, departments: list[str], query: str, limit: int) -> list[dict]:
    """关键词检索面向知识单元层：SQLite FTS5 MATCH。"""
    hits: list[dict] = []
    for row in fts_search_chunks(user_id, departments, query, limit):
        dept = row["folder_key"]
        meta = {
            "source": row["source"],
            "heading_path": " / ".join(row.get("heading_path") or []),
            "content_type": row.get("content_type"),
            "page": row.get("page"),
        }
        hits.append(_make_hit(dept, row["folder_name"], row["chunk_id"], row["content"], meta))
    return hits


def _fuse(pool: dict[str, dict], hits: list[dict], weight: float, channel: str) -> None:
    """倒数排名融合：同一片段在多路结果里排得越靠前，得分越高。"""
    for rank, hit in enumerate(hits):
        entry = pool.get(hit["id"])
        if entry is None:
            entry = {**hit, "fusion_score": 0.0, "channels": set()}
            pool[hit["id"]] = entry
        elif entry.get("distance") is None and hit.get("distance") is not None:
            entry["distance"] = hit["distance"]
        entry["fusion_score"] += weight / (RRF_K + rank + 1)
        entry["channels"].add(channel)


def _unique_queries(queries: list[str]) -> list[str]:
    seen: list[str] = []
    for query in queries:
        text = " ".join((query or "").split())[:500]
        if text and text not in seen:
            seen.append(text)
    return seen


def _log_hits(query: str, hits: list[dict], reranked: bool) -> None:
    mode = "重排" if reranked else "融合"
    print(f"[RETRIEVE] query={query[:80]!r} 返回 {len(hits)} 条（{mode}）", flush=True)
    for hit in hits:
        score = hit.get("rerank_score", hit.get("fusion_score"))
        channels = "+".join(sorted(hit.get("channels") or []))
        print(f"  - {score:.4f} [{channels}] {hit['source']} | {' '.join(hit['content'].split())[:60]}", flush=True)


def search_departments(
    user_id: int,
    departments: list[str],
    query_text: str,
    n_results: int = RETRIEVAL_TOP_K,
    extra_queries: list[str] | None = None,
) -> list[dict]:
    """混合检索：向量走 Chroma，关键词走知识单元 FTS5，RRF 融合后重排。

    departments 是路由选中的文件夹。SEARCH_ALL_FOLDERS 开启时其余文件夹也会检索，只是融合权重更低。
    """
    started_at = time.perf_counter()
    queries = _unique_queries([query_text, *(extra_queries or [])])
    if not queries:
        return []
    catalog = folder_map(user_id)
    routed = [dept for dept in departments if dept in catalog]
    targets = list(catalog) if SEARCH_ALL_FOLDERS else routed
    if not targets:
        return []

    pool: dict[str, dict] = {}
    pending: list[tuple[str, int]] = []
    with _lock:
        client = get_chroma_client()
        for dept in targets:
            try:
                count = client.get_collection(collection_name(user_id, dept)).count()
            except Exception:
                continue
            if count:
                pending.append((dept, count))

        if pending:
            query_embeddings = get_embedding_function()(queries)
            for dept, count in pending:
                dept_name = catalog[dept].get("name", dept)
                weight = 1.0 if not routed or dept in routed else UNROUTED_FOLDER_WEIGHT
                limit = min(RECALL_K, count)
                collection = get_collection(user_id, dept)
                results = collection.query(
                    query_embeddings=query_embeddings,
                    n_results=limit,
                    include=["documents", "metadatas", "distances"],
                )
                for position, _query in enumerate(queries):
                    _fuse(pool, _vector_hits(dept, dept_name, results, position), weight, "vector")

    # 关键词通道直接查规范化知识单元 + FTS5（不依赖 Chroma）
    for query in queries:
        keyword_hits = _keyword_hits(user_id, targets, query, RECALL_K * max(1, len(targets)))
        for hit in keyword_hits:
            weight = 1.0 if not routed or hit["department"] in routed else UNROUTED_FOLDER_WEIGHT
            _fuse(pool, [hit], weight, "keyword")

    if not pool:
        return []

    recalled_at = time.perf_counter()
    candidates = sorted(pool.values(), key=lambda hit: hit["fusion_score"], reverse=True)[:RERANK_CANDIDATES]
    try:
        ranked = rerank(queries[0], candidates, n_results)
    except Exception as exc:
        print(f"[WARN] 重排失败，改用融合排序: {exc}", flush=True)
        ranked = None
    hits = ranked if ranked is not None else candidates[:n_results]
    if NEIGHBOR_EXPAND > 0 and hits:
        with _lock:
            hits = _expand_neighbors(user_id, hits)
    print(
        f"[TIMING] 召回 {recalled_at - started_at:.2f}s（{len(pending)} 个向量库，{len(candidates)} 个候选）"
        f" | 重排 {time.perf_counter() - recalled_at:.2f}s",
        flush=True,
    )
    _log_hits(queries[0], hits, ranked is not None)
    for hit in hits:
        hit["channels"] = sorted(hit.get("channels") or [])
    return hits


def _chunk_prefix_and_index(hit: dict) -> tuple[str | None, int | None]:
    raw_id = str(hit.get("id") or "").split(":", 1)[-1]
    marker = "_chunk_"
    if marker not in raw_id:
        return None, None
    prefix, _, index_text = raw_id.rpartition(marker)
    try:
        return f"{prefix}{marker}", int(index_text)
    except ValueError:
        return None, None


def _chunk_index(hit: dict) -> int | None:
    return _chunk_prefix_and_index(hit)[1]


def _expand_neighbors(user_id: int, hits: list[dict]) -> list[dict]:
    """命中某块时带上前后相邻知识单元，补全被切开的同一章节内容。"""
    selected: list[dict] = []
    seen: set[str] = set()

    def add(hit: dict) -> None:
        hit_id = hit.get("id")
        if not hit_id or hit_id in seen or len(selected) >= MAX_CONTEXT_CHUNKS:
            return
        seen.add(hit_id)
        selected.append(hit)

    for hit in hits:
        add(hit)
        prefix, index = _chunk_prefix_and_index(hit)
        if prefix is None or index is None:
            continue
        want = [f"{prefix}{index + offset}" for offset in range(-NEIGHBOR_EXPAND, NEIGHBOR_EXPAND + 1) if offset]
        neighbors_rows = get_knowledge_chunks_by_ids(user_id, want)
        neighbors = [
            _make_hit(
                row["folder_key"],
                row["folder_name"],
                row["chunk_id"],
                row["content"],
                {"source": row["source"], "heading_path": " / ".join(row.get("heading_path") or [])},
            )
            for row in neighbors_rows
        ]
        neighbors.sort(key=lambda item: _chunk_index(item) or 0)
        for neighbor in neighbors:
            neighbor["channels"] = set(hit.get("channels") or []) | {"neighbor"}
            neighbor["fusion_score"] = hit.get("fusion_score", 0)
            if "rerank_score" in hit:
                neighbor["rerank_score"] = hit["rerank_score"]
            add(neighbor)
        if len(selected) >= MAX_CONTEXT_CHUNKS:
            break
    return selected
