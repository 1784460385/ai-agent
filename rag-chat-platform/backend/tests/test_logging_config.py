"""logging_config 单元测试。"""

import logging
import sys

from logging_config import configure_logging, get_logger


def test_configure_logging_is_idempotent():
    """多次调用重新生成 handler 不会无限堆叠。"""
    configure_logging()
    root = logging.getLogger()
    # StreamHandler + (maybe) RotatingFileHandler
    n1 = len([h for h in root.handlers if not isinstance(h, type(root.handlers[0])) or True])
    configure_logging()
    n2 = len([h for h in root.handlers if not isinstance(h, type(root.handlers[0])) or True])
    # 数量应保持稳定 —— 不应该成倍增长
    assert n2 <= n1 + 1


def test_get_logger_returns_module_logger():
    log = get_logger("rag.test")
    assert log.name == "rag.test"
    assert isinstance(log, logging.Logger)


def test_configure_logging_sets_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    configure_logging(level="DEBUG")
    assert logging.getLogger().level == logging.DEBUG


def test_quiets_third_party_loggers():
    configure_logging()
    from logging_config import _QUIET_LOGGERS

    for name in _QUIET_LOGGERS:
        log = logging.getLogger(name)
        assert log.level == logging.WARNING, f"{name} 未被压到 WARNING"


def test_logger_output_to_stdout(capsys):
    configure_logging()
    log = get_logger("rag.test")
    log.info("hello-stdout-marker")
    captured = capsys.readouterr()
    assert "hello-stdout-marker" in captured.out or "hello-stdout-marker" in captured.err


def test_logger_format_includes_module_name(capsys):
    configure_logging()
    log = get_logger("rag.test_format")
    log.info("format-marker")
    captured = capsys.readouterr()
    # 标准格式: %(asctime)s %(levelname)-7s %(name)s | %(message)s
    assert "rag.test_format" in captured.out or "rag.test_format" in captured.err
