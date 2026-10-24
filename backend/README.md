# 后端

分层实现，只依赖 Python 标准库；使用 MySQL 时额外需要 `PyMySQL`。

## 分层

```text
web.py          HTTP 传输层（Bearer 令牌提取、JSON 收发、静态资源、异常翻译）
api/router.py   接口层（路由表、参数校验、令牌 → actor）
services/       业务层（auth / reservation / violation / recommendation / stats / admin + 纯规则）
repositories/   仓储层（只写 SQL，含会话表 session_repository）
security.py     安全原语（PBKDF2 口令哈希、令牌生成与摘要）
events.py       进程内事件总线（SSE 数据源）
db.py           数据底座（连接池、事务、加锁、双方言适配）
config.py       配置（环境变量）
sweeper.py      违规扫描后台线程
app.py          装配入口（含明文口令迁移）
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
| `SESSION_TTL_DAYS` | 7 | 登录令牌有效期（天，登录时刻起算） |
| `CORS_ORIGIN` | `*` | 允许的跨域来源，部署时收敛 |
| `CHECKIN_EARLY_MINUTES` | 30 | 开始前多少分钟开放签到 |
| `CHECKIN_ENFORCED` | 1 | 是否强制校验签到窗口（0 关闭） |
| `SSE_HEARTBEAT_SECONDS` | 15 | SSE 心跳间隔（无事件时发注释帧保活） |
| `SSE_MAX_CLIENTS` | 50 | SSE 最大同时连接数（每个连接占一个线程） |
| `PBKDF2_ITERATIONS` | 200000 | 口令哈希迭代次数（仅测试调低） |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | 监听地址 |
| `NO_SHOW_GRACE_MINUTES` | 15 | 超时未签到宽限 |
| `OVERSTAY_GRACE_MINUTES` | 30 | 超时占用宽限 |
| `VIOLATION_WINDOW_DAYS` / `VIOLATION_BLOCK_THRESHOLD` | 30 / 3 | 违规统计窗口与限制预约阈值 |
| `SWEEPER_INTERVAL` | 60 | 违规扫描间隔（秒），0 表示只保留手动触发 |

## 鉴权

除 `/api/health` 与 `/api/login` 外，所有接口都要求：

```http
Authorization: Bearer <token>
```

- 登录成功后返回 `token` 与 `expires_at`，服务端只保存令牌的 SHA-256 摘要（`sessions` 表）；
- 口令以 PBKDF2-HMAC-SHA256（20 万次迭代 + 每用户独立盐）存储；存量明文口令在启动时自动迁移；
- 接口不再接受 `user_id` 参数，身份一律由令牌解析，管理员权限由 `require_admin(actor)` 校验；
- `POST /api/logout` 立即失效当前令牌。

## 实时推送

`GET /api/events?token=<token>` 返回 `text/event-stream`（chunked），事件由 `events.py` 的事件总线广播：

- 预约创建/取消/签到/结束、座位维护、违规扫描/处理都会 `bus.publish(...)`；
- 发布方不阻塞：订阅队列满时丢最旧事件；订阅数超过 `SSE_MAX_CLIENTS` 返回 503；
- 单进程实现；多进程部署把 `EventBus` 换成 Redis Pub/Sub 即可，调用方不变。

## 测试

```powershell
python -m unittest discover -s tests -t . -v
```

测试默认跑在临时 SQLite 库上；设置 `TEST_DB_BACKEND=mysql` 可在 MySQL 实例上执行同一套用例。
