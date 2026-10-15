"""日志配置中心。

设计原则:
- 入口 main.py 调用一次 configure_logging(),后续模块直接 getLogger(__name__)
- 日志级别由 LOG_LEVEL 环境变量控制,默认 INFO
- 同时输出到 stdout(供容器/docker)和到 logs/app.log(供本地排查)
- 第三方库(huggingface/chromadb/openai 等)打到 WARNING,避免刷屏

模块命名约定(便于按用途过滤):
- rag.* —— 业务日志
- rag.retrieve —— 检索 / 重排
- rag.index —— 索引 / 摄取
- rag.embed —— embedding / reranker 模型加载
- rag.llm —— LLM 调用 / 路由
- rag.io —— 文件解析 / OCR / 下载
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import BASE_DIR

DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"

# 默认级别,通过 LOG_LEVEL=DEBUG 覆盖
DEFAULT_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# 已知会刷屏的第三方库
_QUIET_LOGGERS = (
    "httpx",
    "httpcore",
    "urllib3",
    "chromadb",
    "sentence_transformers",
    "transformers",
    "huggingface_hub",
    "openai",
    "torch",
    "filelock",
    "onnxruntime",
)


def configure_logging(*, level: str | None = None) -> None:
    """初始化根 logger。

    调用一次即可,通常在 main.py 的 lifespan 启动阶段调用。
    """
    import sys

    resolved_level = (level or DEFAULT_LEVEL or "INFO").upper()
    root = logging.getLogger()
    # 先清掉已有的 handler,避免和 uvicorn / pytest 自身的日志打架,
    # 也避免 StreamHandler 持有的 sys.stdout 引用过期
    for h in list(root.handlers):
        root.removeHandler(h)

    root.setLevel(resolved_level)

    formatter = logging.Formatter(DEFAULT_FORMAT, datefmt=DEFAULT_DATEFMT)
    # 不传 stream=sys.stdout,让 StreamHandler 内部用 sys.__stdout__,避免
    # pytest / 测试夹具替换 sys.stdout 之后日志被吞。
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    # 选配:文件日志
    log_dir = Path(os.getenv("LOG_DIR", str(BASE_DIR / "logs")))
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=int(os.getenv("LOG_FILE_MAX_BYTES", str(10 * 1024 * 1024))),
            backupCount=int(os.getenv("LOG_FILE_BACKUP_COUNT", "5")),
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # 磁盘满 / 权限不够时静默退化为只输出 stdout
        pass

    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """模块级 logger 工厂。统一从 configure_logging() 拿到的根配置。"""
    return logging.getLogger(name)
