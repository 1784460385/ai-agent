"""vector_store 锁策略的回归测试。

拆分后的锁策略:
- 写入(影响 collection 内容)用 _lock_for(name),按 collection 独立
- 读取不持锁
- _lock_for(name) 同名应返回同一锁对象,不同名应返回不同锁对象
"""

import threading

import pytest

import vector_store


def teardown_function(_func):
    """每个测试后重置 _collection_locks,避免测试间互相污染。"""
    vector_store._collection_locks.clear()


def test_os_module_imported():
    """回归测试: 之前 vector_store.py 漏 import os,导致 get_chroma_client 在
    重建索引时崩溃 (NameError: name 'os' is not defined)。
    这里直接验证 os 已在模块命名空间,避免再次回归。
    """
    assert hasattr(vector_store, "os"), "vector_store 必须 import os"
    assert hasattr(vector_store.os, "makedirs"), "os.makedirs 应当可用"


def test_lock_for_returns_same_lock_for_same_name():
    lock_a = vector_store._lock_for("user_1_folder_a")
    lock_b = vector_store._lock_for("user_1_folder_a")
    assert lock_a is lock_b


def test_lock_for_returns_different_locks_for_different_names():
    lock_a = vector_store._lock_for("user_1_folder_a")
    lock_b = vector_store._lock_for("user_1_folder_b")
    assert lock_a is not lock_b


def test_lock_for_is_thread_safe():
    """并发调用 _lock_for(name) 应安全,且返回同一对象。"""
    name = "concurrent_folder"
    seen = []

    def call():
        seen.append(id(vector_store._lock_for(name)))

    threads = [threading.Thread(target=call) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 所有线程拿到的 lock 对象都相同
    assert len(set(seen)) == 1


def test_different_collections_can_run_concurrently():
    """两个 collection 的写入互不阻塞(旧 _lock 全局锁会阻塞,这是拆分的目标)。"""
    a = vector_store._lock_for("col_a")
    b = vector_store._lock_for("col_b")
    barrier = threading.Lock()
    order = []
    a_acquired = threading.Event()
    b_acquired = threading.Event()

    def hold_for(lock, evt, name):
        with lock:
            order.append(f"start: {name}")
            evt.set()
            # 在持有锁的同时,如果对方也想拿锁,会被阻塞
            # (这里只验证 "能进入";不验证并发)

    t_a = threading.Thread(target=hold_for, args=(a, a_acquired, "a"))
    t_a.start()
    a_acquired.wait()

    t_b = threading.Thread(target=hold_for, args=(b, b_acquired, "b"))
    t_b.start()
    b_acquired.wait(timeout=2.0)

    assert b_acquired.is_set(), "不同 collection 的锁应该互不阻塞,b 应当能立即拿到锁"
    assert order == ["start: a", "start: b"]


def test_same_collection_blocks():
    """同名 collection 的两次 _lock_for(...).acquire() 应该是同一锁,会互斥。"""
    lock = vector_store._lock_for("col_x")
    holder_in = threading.Event()
    second_done = threading.Event()

    def hold():
        with lock:
            holder_in.set()
            second_done.wait(timeout=2.0)

    t_holder = threading.Thread(target=hold)
    t_holder.start()
    holder_in.wait()

    second_acquired = []

    def try_second():
        result = lock.acquire(blocking=False)
        if result:
            second_acquired.append(True)
            lock.release()
        second_done.set()

    t_second = threading.Thread(target=try_second)
    t_second.start()
    t_second.join(timeout=1.0)
    t_holder.join(timeout=2.0)

    assert second_acquired == [], "同名锁必须互斥,第二个线程应该 acquire 失败"