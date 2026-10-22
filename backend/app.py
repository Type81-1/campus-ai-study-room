"""应用装配入口。

启动顺序：初始化数据库（建表 + 演示数据）→ 装配服务 → 启动违规扫描线程 → 提供 HTTP 服务。

运行方式（二选一）：
    python backend/server.py
    python -m backend.app
"""
from __future__ import annotations

from .api.router import Api
from .config import config
from .db import Database
from .sweeper import ViolationSweeper
from .web import make_server


def bootstrap(cfg=config):
    """返回 (database, api)：初始化库结构并装配服务，供启动脚本与测试复用。"""
    db = Database(cfg)
    db.initialize()
    return db, Api(db)


def run(host: str | None = None, port: int | None = None, cfg=config) -> None:
    host = host or cfg.host
    port = port or cfg.port

    db, api = bootstrap(cfg)
    info = cfg.describe()
    print("校园 AI 智能自习室预约系统已启动")
    print(f"  访问地址：http://{host}:{port}")
    print(f"  数据库：{info['database']}（{info['backend']}）")
    print(f"  违规规则：超时未签到 {info['no_show_grace_minutes']} 分钟 / "
          f"超时占用 {info['overstay_grace_minutes']} 分钟 / "
          f"累计 {info['violation_block_threshold']} 条限制预约")

    sweeper = None
    if cfg.sweeper_interval > 0:
        sweeper = ViolationSweeper(api.violations, cfg.sweeper_interval)
        sweeper.start()
        sweeper.scan_once()  # 启动时先扫一遍，避免上一轮遗漏

    server = make_server(api, host, port, cfg)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")
    finally:
        if sweeper:
            sweeper.stop()
        server.server_close()


if __name__ == "__main__":
    run(port=None)
