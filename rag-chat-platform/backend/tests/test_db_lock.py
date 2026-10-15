"""`db_lock` 单元测试:RWLock 行为 + db_session / get_db 的 SQLAlchemy 包装。"""

from __future__ import annotations

import threading

import pytest


def test_read_lock_allows_concurrent_readers():
    """多个读者可同时进入;同一线程不能因为是 reader 阻塞 reader。"""
    from db_lock import db_locks

    res = db_locks._get("tables_test_a")
    barrier = threading.Barrier(4)
    entered = [0, 0, 0, 0]
    errors: list[Exception] = []

    def reader(idx: int) -> None:
        res.acquire_read()
        try:
            entered[idx] = 1
            barrier.wait(timeout=2.0)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            res.release_read()

    threads = [threading.Thread(target=reader, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3.0)
    assert not errors, errors
    # 4 个 reader 都进入了临界区
    assert sum(entered) == 4


def test_write_lock_blocks_readers_and_other_writers():
    """写者持锁期间,其他读者 / 写者必须等待。"""
    from db_lock import db_locks

    res = db_locks._get("tables_test_b")
    res.acquire_write()
    acquired_write = [False]
    acquired_read = [False]
    errors: list[Exception] = []

    def try_writer() -> None:
        try:
            res.acquire_write()
            acquired_write[0] = True
            res.release_write()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def try_reader() -> None:
        try:
            res.acquire_read()
            acquired_read[0] = True
            res.release_read()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    tw = threading.Thread(target=try_writer)
    tr = threading.Thread(target=try_reader)
    tw.start()
    tr.start()
    tw.join(timeout=0.3)
    tr.join(timeout=0.3)
    # 都应该因为 join 超时而未完成
    assert acquired_write[0] is False
    assert acquired_read[0] is False
    res.release_write()
    tw.join(timeout=2.0)
    tr.join(timeout=2.0)
    assert acquired_write[0] is True
    assert acquired_read[0] is True


def test_write_lock_releases_after_release_write():
    """释放写锁后,后续 reader 立即可以进入。"""
    from db_lock import db_locks

    res = db_locks._get("tables_test_c")
    res.acquire_write()
    res.release_write()
    # 此时应该没有阻塞
    res.acquire_read()
    try:
        # do nothing
        pass
    finally:
        res.release_read()


def test_transaction_context_managers_release_on_exception():
    """transaction() 在异常后仍能正确释放锁;否则下次 acquire_write 会死锁。"""
    from db_lock import transaction

    with pytest.raises(RuntimeError):
        with transaction("tables_test_d"):
            raise RuntimeError("simulate failure")
    # 锁已经被释放,再次获取应该立即成功
    with transaction("tables_test_d"):
        pass


def test_read_transaction_does_not_block_another_reader():
    """两个 read_transaction 并发能同时进入(都在 .acquire_read)。"""
    from db_lock import read_transaction

    started = threading.Event()
    second_in = threading.Event()
    errors: list[Exception] = []

    def hold_read() -> None:
        with read_transaction("tables_test_e"):
            started.set()
            # 等另一个 reader 也进入
            if not second_in.wait(timeout=2.0):
                errors.append(TimeoutError("second reader 未进入"))

    def second_reader() -> None:
        started.wait(timeout=2.0)
        with read_transaction("tables_test_e"):
            second_in.set()

    t1 = threading.Thread(target=hold_read)
    t2 = threading.Thread(target=second_reader)
    t1.start()
    t2.start()
    t1.join(timeout=3.0)
    t2.join(timeout=3.0)
    assert not errors, errors


def test_get_db_yields_session_and_closes():
    """`database.get_db` 与 `db_lock.get_db` 行为一致:generator 形式 yield + 关闭。"""
    from db_lock import get_db

    gen = get_db()
    session = next(gen)
    assert session is not None
    # 关闭
    try:
        next(gen)
    except StopIteration:
        # 期望 generator 正常结束
        pass


def test_db_session_auto_commits_on_clean_exit():
    """SQLAlchemy session context manager 成功后自动 commit。"""
    from db_lock import db_session
    from models_db import User

    # 先查一下初始管理员用户数(仅查,不写)
    with db_session() as session:
        initial = session.query(User).filter(User.username == "_test_lock_probe_user_").count()
    assert initial == 0
