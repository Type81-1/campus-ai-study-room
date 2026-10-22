# 后端

分层实现，只依赖 Python 标准库；使用 MySQL 时额外需要 `PyMySQL`。

## 分层

```text
web.py          HTTP 传输层（JSON 收发、静态资源、异常翻译）
api/router.py   接口层（路由表、参数校验）
services/       业务层（auth / reservation / violation / recommendation / stats + 纯规则）
repositories/   仓储层（只写 SQL）
db.py           数据底座（连接池、事务、加锁、双方言适配）
config.py       配置（环境变量）
sweeper.py      违规扫描后台线程
app.py          装配入口
```

## 启动

```powershell
# SQLite（零依赖）
python backend/server.py

# MySQL
$env:DB_BACKEND="mysql"; $env:MYSQL_HOST="127.0.0.1"; $env:MYSQL_USER="root"; $env:MYSQL_PASSWORD="studyroom"
python backend/server.py
```

默认 <http://127.0.0.1:8000>。演示账号：`student001 / 123456`、`admin / admin123`。

## 配置项

全部通过环境变量注入，样例见根目录 `.env.example`：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DB_BACKEND` | 自动 | `mysql` / `sqlite`；不填时按是否配置 `MYSQL_HOST` 判断 |
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | — | MySQL 连接参数 |
| `MYSQL_POOL_SIZE` | 8 | 连接池大小 |
| `STUDY_ROOM_DB` | `backend/data/study_room.db` | SQLite 库文件路径 |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | 监听地址 |
| `NO_SHOW_GRACE_MINUTES` | 15 | 超时未签到宽限 |
| `OVERSTAY_GRACE_MINUTES` | 30 | 超时占用宽限 |
| `VIOLATION_WINDOW_DAYS` / `VIOLATION_BLOCK_THRESHOLD` | 30 / 3 | 违规统计窗口与限制预约阈值 |
| `SWEEPER_INTERVAL` | 60 | 违规扫描间隔（秒），0 表示只保留手动触发 |

## 测试

```powershell
python -m unittest discover -s tests -t . -v
```

测试默认跑在临时 SQLite 库上；设置 `TEST_DB_BACKEND=mysql` 可在 MySQL 实例上执行同一套用例。
