import hashlib
import json
import re
import shutil
import threading
from pathlib import Path

from config import KNOWLEDGE_BASE_DIR
from database import delete_folder_row, get_folder, insert_folder, list_folders, sync_catalog

LEGACY_FOLDERS = {
    "finance": {
        "name": "财务部",
        "description": "计费、报销、发票、工资等财务资料",
        "keywords": ["工资", "报销", "发票", "财务", "计费", "收费", "付款", "薪资", "税率", "预算", "额度"],
    },
    "hr": {
        "name": "人事部",
        "description": "入职、假期、考勤、绩效等人事资料",
        "keywords": ["入职", "请假", "假期", "年假", "考勤", "人事", "招聘", "绩效", "离职", "社保", "公积金"],
    },
    "tech": {
        "name": "技术部",
        "description": "接口、部署、故障排查等技术资料",
        "keywords": ["API", "接口", "部署", "故障", "代码", "技术", "架构", "数据库", "服务器", "运维"],
    },
    "product": {
        "name": "产品部",
        "description": "产品功能、版本、客服等产品资料",
        "keywords": ["产品", "功能", "需求", "版本", "更新", "用户手册", "原型", "设计", "客服"],
    },
}

_INVALID = re.compile(r'[\\/:*?"<>|]')
_lock = threading.Lock()


def root() -> Path:
    path = Path(KNOWLEDGE_BASE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _collection_id(folder_key: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,40}", folder_key):
        return f"kb_{folder_key.lower()}"
    return "kb_" + hashlib.sha1(folder_key.encode("utf-8")).hexdigest()[:16]


def _meta_from_dir(path: Path) -> dict:
    meta_path = path / ".folder.json"
    data: dict = {}
    if meta_path.is_file():
        try:
            loaded = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError):
            data = {}
    if not data:
        legacy = LEGACY_FOLDERS.get(path.name, {})
        data = {
            "name": legacy.get("name", path.name),
            "description": legacy.get("description", path.name),
            "keywords": legacy.get("keywords", [legacy.get("name", path.name)]),
            "collection": _collection_id(path.name),
        }
    name = str(data.get("name") or path.name)
    description = str(data.get("description") or name)
    keywords = data.get("keywords")
    if not isinstance(keywords, list):
        keywords = [name]
    cleaned_keywords = [str(item) for item in keywords if str(item).strip()]
    return {
        "key": path.name,
        "name": name,
        "description": description,
        "keywords": cleaned_keywords or [name],
        "collection": str(data.get("collection") or _collection_id(path.name)),
    }


def sync_from_disk() -> None:
    with _lock:
        sync_catalog(_meta_from_dir)


def folder_map() -> dict[str, dict]:
    return {folder["key"]: folder for folder in list_folders()}


def validate_folder_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned or cleaned in {".", ".."} or cleaned.startswith("."):
        raise ValueError("请输入文件夹名称")
    if _INVALID.search(cleaned) or len(cleaned) > 40:
        raise ValueError("文件夹名称不能包含 \\ / : * ? \" < > |，且不超过 40 个字")
    return cleaned


def create_folder(name: str) -> dict:
    cleaned = validate_folder_name(name)
    with _lock:
        if get_folder(cleaned) is not None or (root() / cleaned).exists():
            raise ValueError("同名文件夹已存在")
        path = root() / cleaned
        try:
            path.mkdir(parents=False)
        except FileExistsError as exc:
            raise ValueError("同名文件夹已存在") from exc
        meta = {
            "key": cleaned,
            "name": cleaned,
            "description": cleaned,
            "keywords": [cleaned],
            "collection": _collection_id(cleaned),
        }
        try:
            insert_folder(meta)
        except Exception:
            if path.is_dir():
                path.rmdir()
            raise
        return meta


def delete_folder(folder_key: str) -> None:
    with _lock:
        if get_folder(folder_key) is None:
            raise ValueError("文件夹不存在")
        path = root() / folder_key
        if path.is_dir():
            shutil.rmtree(path)
        delete_folder_row(folder_key)
