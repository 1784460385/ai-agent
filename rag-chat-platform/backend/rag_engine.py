import threading
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import CHUNK_OVERLAP, CHUNK_SIZE
from database import document_blobs
from file_parsers import ParseError, load_bytes
from folders import get_folder, list_folders
from parse_status import set_status


def _load_stored_documents(user_id: int, folder_key: str) -> tuple[list, dict[str, str], list[str]]:
    documents = []
    errors: dict[str, str] = {}
    names: list[str] = []
    for filename, payload in document_blobs(user_id, folder_key):
        names.append(filename)
        try:
            documents.extend(load_bytes(filename, payload))
        except ParseError as exc:
            errors[filename] = str(exc)
            print(f"[WARN] 加载 {filename} 失败: {exc}")
        except Exception as exc:
            errors[filename] = f"解析失败：{exc}"
            print(f"[WARN] 加载 {filename} 失败: {exc}")
    return documents, errors, names


def _source_label(metadata: dict) -> str:
    source = Path(str(metadata.get("source") or "未知文件")).name
    page = metadata.get("page")
    if page is None:
        return source
    try:
        return f"{source} 第{int(page) + 1}页"
    except (TypeError, ValueError):
        return source


def load_and_split_documents(user_id: int, only_department: str | None = None) -> dict:
    """按数据库中的原文分别加载和分块。"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n# ", "\n## ", "\n### ", "\n\n", "\n", "。", "！", "？", "；", " ", ""],
        length_function=len,
    )
    selected = [only_department] if only_department else [folder["key"] for folder in list_folders(user_id)]
    dept_chunks: dict = {}

    for dept in selected:
        if get_folder(user_id, dept) is None:
            continue
        documents, errors, names = _load_stored_documents(user_id, dept)
        _record_parse_results(user_id, dept, names, errors)
        if not documents:
            dept_chunks[dept] = []
            continue
        dept_chunks[dept] = splitter.split_documents(documents)
    return dept_chunks


def _record_parse_results(user_id: int, dept: str, names: list[str], errors: dict[str, str]) -> None:
    for name in names:
        if name in errors:
            set_status(user_id, dept, name, "failed", errors[name])
        else:
            set_status(user_id, dept, name, "indexed")


def index_knowledge_base(user_id: int, only_department: str | None = None):
    """按部门分别索引。"""
    from vector_store import delete_legacy_collection, replace_documents

    dept_chunks = load_and_split_documents(user_id, only_department)
    if not dept_chunks:
        return {"status": "empty", "message": "知识库目录为空或无支持的文档"}

    if only_department is None:
        delete_legacy_collection()

    counts: dict[str, int] = {}
    total = 0
    for dept, chunks in dept_chunks.items():
        texts: list[str] = []
        ids: list[str] = []
        metadatas: list[dict] = []
        dept_name = (get_folder(user_id, dept) or {}).get("name", dept)
        for chunk in chunks:
            content = chunk.page_content.strip()
            if not content:
                continue
            label = f"{dept_name}/{_source_label(chunk.metadata)}"
            title = Path(str(chunk.metadata.get("source") or "")).stem
            texts.append(f"【{title}】\n{content}" if title else content)
            ids.append(f"{dept}_chunk_{len(ids)}")
            metadatas.append({"source": label, "department": dept, "chunk": len(ids) - 1})
        count = replace_documents(user_id, dept, texts, ids, metadatas)
        counts[dept] = count
        total += count
        print(f"[INDEX] {dept}: 索引了 {count} 个片段")

    if total == 0:
        return {"status": "empty", "message": "知识库目录为空或无支持的文档", "departments": counts}
    return {"status": "ok", "chunks_indexed": total, "departments": counts}


def ingest_saved_file(user_id: int, department: str, filename: str) -> None:
    """先在时限内解析数据库中的原文，成功后再重建该部门索引。"""
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as FuturesTimeout

    from config import PARSE_TIMEOUT_SECONDS
    from database import read_document_bytes
    from file_parsers import ParseError, load_bytes

    payload = read_document_bytes(user_id, department, filename)
    if payload is None:
        set_status(user_id, department, filename, "failed", "文件不存在")
        return
    set_status(user_id, department, filename, "parsing")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(load_bytes, filename, payload)
            future.result(timeout=PARSE_TIMEOUT_SECONDS)
    except FuturesTimeout:
        set_status(user_id, department, filename, "failed", "解析超时")
        return
    except ParseError as exc:
        set_status(user_id, department, filename, "failed", str(exc))
        return
    except Exception as exc:
        set_status(user_id, department, filename, "failed", f"解析失败：{exc}")
        return

    with _ingest_lock:
        try:
            index_knowledge_base(user_id, department)
        except Exception as exc:
            set_status(user_id, department, filename, "failed", f"索引失败：{exc}")


_ingest_lock = threading.Lock()


NO_KB_NOTICE = "知识库中没有可引用的内容，以下由模型自行生成，请自行判断准确性。"


def build_rag_prompt(user_question: str, retrieved_docs: list[str]) -> str:
    """构建增强 Prompt。"""
    context = "\n\n---\n\n".join(retrieved_docs) if retrieved_docs else "（知识库中没有检索到相关内容）"
    return f"""你是一个知识库助手。优先根据上下文回答；上下文没有依据时，再用你自己的知识回答。

规则：
1. 先逐条检查上下文。只要有片段与问题相关（包括提到了问题中的关键词、名称、编号，或能回答问题的一部分），就必须优先依据这些片段作答，并标注来源。
2. 上下文只能回答一部分时，先按上下文回答能回答的部分并标注来源，再说明哪些部分知识库没有覆盖，可以用你自己的知识补充，补充部分要明确标为"补充说明"。
3. 只有当上下文为空，或所有片段都与问题完全无关时，才用你自己的知识完整回答，并且回答的第一句必须原样写出：{NO_KB_NOTICE}
4. 不要罗列与问题无关的资料；自行生成时不要把上下文说成来源，也不要编造知识库里不存在的出处。

## 上下文信息
{context}

## 用户问题
{user_question}"""
