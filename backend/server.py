"""向后兼容的启动脚本：python backend/server.py

真正的实现已按分层拆分到 backend/ 下的各模块，这里只保留入口，方便沿用原有启动命令。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app import run  # noqa: E402

if __name__ == "__main__":
    run()
