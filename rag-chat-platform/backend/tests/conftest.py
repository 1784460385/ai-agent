# ---- 测试公用配置 ----
#
# 让 pytest 能 import backend/* 顶层模块,同时设置最小环境变量,
# 避免某些模块的 setdefault 在 setUp 之前 import 时拿不到值。

import sys
from pathlib import Path

# 让 backend 目录可被 import
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 所有 HF / Chroma 默认值集中在 config.apply_env();先 import config 触发
import config  # noqa: E402

config.apply_env()
