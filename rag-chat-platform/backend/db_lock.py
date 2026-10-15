"""数据库并发控制 + SQLAlchemy/裸 sqlite3 统一接入。

核心目标
=========

#2 统一 DB —— 历史代码同时使用 ``sqlite3`` 裸连接和 SQLAlchemy Session,
所有数据库访问又串在一个模块级 ``threading.RLock`` 上,导致:

* 多用户读请求互相串行
* 一次长查询期间,任何小写都会被阻塞
* SQLAlchemy ``Session`` 用 ``check_same_thread=False`` 跨线程,容易锁等待

本模块提供
----------

1. ``db_locks`` —— 按"资源名"分组的可重入读写锁。读不互斥,写互斥所有读和其它写。
2. ``transaction()`` —— 显式事务包装,使用时获取写锁;事务结束自动 commit/rollback。
3. ``read_transaction()`` —— 只读事务包装,获取读锁,允许并发读取。
4. ``db_session()`` —— SQLAlchemy ``Session`` 上下文管理器;自动 commit/rollback,
   与裸 sqlite3 共享同一个 SQLite 文件(WAL 模式下两边都可读可写)。
5. ``session_scope()`` —— 同样是 SQLAlchemy session,但向上层以 dependency / 装饰器
   形式暴露(``SessionLocal`` + ``get_db`` 仍保留以兼容旧路由)。

调用约定
---------

业务代码::

    from db_lock import db_locks, transaction, read_transaction

    # 读
    with read_transaction("folders"):
        rows = conn.execute(...).fetchall()

    # 写
    with transaction("folders"):
        conn.execute(...)
        conn.execute(...)

History / chat 路由用 SQLAlchemy::

    from db_lock import db_session

    with db_session() as session:
        session.add(Conversation(...))

把模块级 ``_lock`` 替换成 ``db_locks["<resource>"]`` 是渐进的,无需一次性重写全库。
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session

from database import SessionLocal

_log = logging.getLogger("rag.db")


class _RWLock:
    """可重入读写锁。

    同一线程可多次获取读锁;写锁阻塞所有读和其它写。
    适合 SQLite + WAL 场景:多读者 + 单写者,最大化读并发。
    """

    def __init__(self) -> None:
        self._readers = 0
        self._writer: threading.Thread | None = None
        # writers + readers 各自的等待数:用 Condition 而不是事件避免惊群
        self._cond = threading.Condition(threading.Lock())
        self._writer_depth = 0  # 写锁可重入计数

    def acquire_read(self) -> None:
        with self._cond:
            owner = threading.current_thread()
            while self._writer is not None and self._writer is not owner:
                self._cond.wait()
            self._readers += 1

    def release_read(self) -> None:
        with self._cond:
            self._readers -= 1
            if self._readers == 0:
                self._cond.notify_all()

    def acquire_write(self) -> None:
        with self._cond:
            owner = threading.current_thread()
            depth = 0
            while True:
                if self._writer is owner:
                    # 同一线程可重入
                    self._writer_depth += 1
                    return
                if self._writer is None and self._readers == 0:
                    self._writer = owner
                    self._writer_depth = 1
                    return
                depth += 1
                self._cond.wait()

    def release_write(self) -> None:
        with self._cond:
            self._writer_depth -= 1
            if self._writer_depth == 0:
                self._writer = None
                self._cond.notify_all()


class _DBLocks:
    """按资源名分组的 RWLock 集合。

    用法::

        db_locks["folders"].acquire_read()
        try:
            ...
        finally:
            db_locks["folders"].release_read()

    也提供 ``transaction()`` / ``read_transaction()`` context manager,自动获取与释放。
    """

    def __init__(self) -> None:
        self._registry: dict[str, _RWLock] = {}
        self._registry_lock = threading.Lock()

    def _get(self, name: str) -> _RWLock:
        with self._registry_lock:
            lock = self._registry.get(name)
            if lock is None:
                lock = _RWLock()
                self._registry[name] = lock
            return lock

    def __getitem__(self, name: str) -> _RWLock:
        return self._get(name)

    def stats(self) -> dict[str, dict]:
        with self._registry_lock:
            return {
                name: {
                    "readers": lock._readers,
                    "writer": lock._writer is not None,
                }
                for name, lock in self._registry.items()
            }


db_locks = _DBLocks()


@contextmanager
def transaction(name: str) -> Iterator[None]:
    """获取资源的写锁并显式事务。

    配合 ``with db() as conn:`` 使用时:

    .. code-block:: python

        with transaction("knowledge_chunks"):
            with db() as conn:
                conn.execute(...)

    锁会自动释放;SQLite 事务的 commit/rollback 由 ``db()`` 自己负责。
    """
    lock = db_locks[name]
    lock.acquire_write()
    try:
        yield
    finally:
        lock.release_write()


@contextmanager
def read_transaction(name: str) -> Iterator[None]:
    """获取资源的读锁。

    多个 ``read_transaction`` 可并发;会被 ``transaction`` 阻塞。
    """
    lock = db_locks[name]
    lock.acquire_read()
    try:
        yield
    finally:
        lock.release_read()


@contextmanager
def db_session() -> Iterator[Session]:
    """SQLAlchemy Session 上下文管理器。

    自动 commit / rollback;异常向上抛。
    共享 :data:`database.engine` 的连接池,与裸 sqlite3 共用同一文件(WAL 模式)。
    """
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            _log.exception("SQLAlchemy rollback 失败")
        raise
    finally:
        session.close()


# 兼容旧的 ``get_db`` 接口(用于 FastAPI Depends)
def get_db():
    """FastAPI 路由依赖注入式接口。"""
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            _log.exception("SQLAlchemy rollback 失败")
        raise
    finally:
        session.close()
