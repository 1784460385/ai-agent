import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", str(BASE_DIR / "chroma_db"))
KNOWLEDGE_BASE_DIR = os.getenv("KNOWLEDGE_BASE_DIR", str(BASE_DIR / "knowledge_base"))


def sqlite_path() -> Path:
    """应用库路径。每次读取环境变量，便于测试替换。"""
    return Path(os.getenv("SQLITE_PATH", str(BASE_DIR / "app.db")))


JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 7)))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "knowledge_base")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

# 部门配置：目录名、中文名、关键词（规则路由）
DEPARTMENTS = {
    "finance": {
        "name": "财务部",
        "description": "包含公司计费说明、报销制度、发票管理、工资发放等财务相关信息",
        "keywords": ["工资", "报销", "发票", "财务", "计费", "收费", "付款", "薪资", "税率", "预算", "额度"],
    },
    "hr": {
        "name": "人事部",
        "description": "包含员工入职指南、假期管理规定、考勤制度、绩效考核等人事相关信息",
        "keywords": ["入职", "请假", "假期", "年假", "考勤", "人事", "招聘", "绩效", "离职", "社保", "公积金"],
    },
    "tech": {
        "name": "技术部",
        "description": "包含技术文档、API 接口说明、系统部署手册、故障排查指南等技术相关信息",
        "keywords": ["API", "接口", "部署", "故障", "代码", "技术", "架构", "数据库", "服务器", "运维"],
    },
    "product": {
        "name": "产品部",
        "description": "包含产品功能说明、需求文档、版本更新记录、用户手册等产品相关信息",
        "keywords": ["产品", "功能", "需求", "版本", "更新", "用户手册", "原型", "设计", "客服"],
    },
}
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "3"))
RECENT_CONTEXT_TURNS = int(os.getenv("RECENT_CONTEXT_TURNS", "2"))
SUMMARY_TRIGGER_TOKENS = int(os.getenv("SUMMARY_TRIGGER_TOKENS", "800"))
SUMMARY_TRIGGER_TURNS = int(os.getenv("SUMMARY_TRIGGER_TURNS", "2"))
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "deepseek-flash")

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
OFFICE_MAX_BYTES = int(os.getenv("OFFICE_MAX_BYTES", str(50 * 1024 * 1024)))
PARSE_TIMEOUT_SECONDS = int(os.getenv("PARSE_TIMEOUT_SECONDS", "60"))

# 第一、二优先级格式。图片暂不开放上传。
SUPPORTED_FORMATS = [
    {"ext": ".pdf", "label": "PDF", "max_bytes": MAX_UPLOAD_BYTES},
    {"ext": ".docx", "label": "Word", "max_bytes": OFFICE_MAX_BYTES},
    {"ext": ".doc", "label": "Word", "max_bytes": OFFICE_MAX_BYTES},
    {"ext": ".xlsx", "label": "Excel", "max_bytes": OFFICE_MAX_BYTES},
    {"ext": ".xls", "label": "Excel", "max_bytes": OFFICE_MAX_BYTES},
    {"ext": ".pptx", "label": "PowerPoint", "max_bytes": OFFICE_MAX_BYTES},
    {"ext": ".md", "label": "Markdown", "max_bytes": MAX_UPLOAD_BYTES},
    {"ext": ".markdown", "label": "Markdown", "max_bytes": MAX_UPLOAD_BYTES},
    {"ext": ".txt", "label": "TXT", "max_bytes": MAX_UPLOAD_BYTES},
    {"ext": ".html", "label": "HTML", "max_bytes": MAX_UPLOAD_BYTES},
    {"ext": ".htm", "label": "HTML", "max_bytes": MAX_UPLOAD_BYTES},
    {"ext": ".csv", "label": "CSV", "max_bytes": MAX_UPLOAD_BYTES},
    {"ext": ".json", "label": "JSON", "max_bytes": MAX_UPLOAD_BYTES},
    {"ext": ".ipynb", "label": "Notebook", "max_bytes": MAX_UPLOAD_BYTES},
]
COMING_SOON_FORMATS = [
    {"ext": ".jpg", "label": "JPG"},
    {"ext": ".jpeg", "label": "JPEG"},
    {"ext": ".png", "label": "PNG"},
]
ALLOWED_SUFFIXES = {item["ext"] for item in SUPPORTED_FORMATS}
FORMAT_BY_EXT = {item["ext"]: item for item in SUPPORTED_FORMATS}
BLOCKED_SUFFIXES = {".exe", ".dll", ".bat", ".cmd", ".ps1", ".js", ".mjs", ".sh", ".msi", ".zip", ".rar"}


def format_limit_message(suffix: str) -> str:
    spec = FORMAT_BY_EXT.get(suffix)
    if spec is None:
        return "不支持的文件格式"
    limit_mb = spec["max_bytes"] // (1024 * 1024)
    return f"文件超过 {limit_mb}MB（{spec['label']} 上限）"
