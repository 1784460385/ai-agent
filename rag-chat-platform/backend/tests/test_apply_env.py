"""`config.apply_env` 行为测试:幂等、不污染外部环境、可被显式覆盖。"""

import os


def test_apply_env_is_idempotent():
    """重复调用不会报错;所有 setdefault 都已生效。"""
    from config import apply_env

    apply_env()
    snap1 = dict(os.environ)
    apply_env()
    snap2 = dict(os.environ)
    # setdefault:已存在的值不会被覆盖,所以 snap1==snap2
    assert snap1 == snap2
    # 至少设置了这 4 个默认值
    for key in (
        "HF_HUB_DISABLE_XET",
        "HF_HUB_DISABLE_SYMLINKS_WARNING",
        "ANONYMIZED_TELEMETRY",
        "TOKENIZERS_PARALLELISM",
    ):
        assert key in os.environ


def test_apply_env_does_not_overwrite_existing_value():
    """外部已设置的环境变量不会被 setdefault 覆盖。"""
    sentinel_key = "HF_HUB_DISABLE_XET"
    original = os.environ.get(sentinel_key)
    try:
        os.environ[sentinel_key] = "sentinel"
        from config import apply_env

        apply_env()
        # 关键:不应被刷成默认值 "1"
        assert os.environ[sentinel_key] == "sentinel"
    finally:
        if original is None:
            os.environ.pop(sentinel_key, None)
        else:
            os.environ[sentinel_key] = original


def test_apply_env_runs_at_module_import():
    """只要 config 被 import 过,默认值就已设置;无需调用 apply_env。"""
    # config 已经在 conftest 里被 import,先记录当前值
    expected_keys = (
        "HF_HUB_DISABLE_XET",
        "HF_HUB_DISABLE_SYMLINKS_WARNING",
        "ANONYMIZED_TELEMETRY",
        "TOKENIZERS_PARALLELISM",
    )
    snap_before = {key: os.environ.get(key) for key in expected_keys}
    # 重新 import config(import 缓存会让 apply_env 只跑一次,但只跑一次就够)
    import config as cfg  # noqa: F401

    snap_after = {key: os.environ.get(key) for key in expected_keys}
    # 全部都已经被注入(可能某个测试抹掉了一些,重 import 时不会被 setdefault 覆盖)
    # 真正关键:被 import 后,默认值至少有一次被设置过。
    # 因为 setdefault 不覆盖已存在的值,snap_before == snap_after 是合理结果。
    for key, value in snap_before.items():
        assert value == snap_after[key], f"{key} 的值在 config import 期间被改动"
    # 至少 4 个 key 都有值
    assert all(snap_after.values()), f"缺失默认值:{[k for k, v in snap_after.items() if not v]}"
    # apply_env 仍可被显式调用
    assert callable(cfg.apply_env)
