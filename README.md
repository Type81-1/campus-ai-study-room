# 校园 AI 智能自习室预约系统

《软件工程基础》课程设计 选题 1：校园 AI 智能自习室预约系统。

覆盖座位预约、时段锁定、违规占座预警、空闲座位智能推荐、签到核销、后台权限管理与预约数据统计，采用**分层架构 + MySQL + 令牌鉴权** 实现，并配有单元测试、集成测试、并发压力测试与前端无头冒烟测试。

---

## 本版（v2.2）主要改动

| 项 | 改动 |
| --- | --- |
| 实时推送 | 新增 `GET /api/events`（SSE）：别人下单/取消/签到/座位维护后，当前页 1 秒内自动刷新；断线自动重连，顶栏显示「实时/离线」 |
| 推荐算法 | v2 增加两个可解释因子（冷门座位、前后时段连续空闲），并返回时段热度（占用率 + 紧张程度 + 建议） |
| 前端打磨 | 修复提示条遮挡顶栏、管理页标题重复、趋势图日期截断、窄屏品牌文字溢出与表格撑破页面；补 favicon |
| 测试体系 | 新增 SSE 协议级测试（裸 socket）、事件总线单测、Playwright 真实浏览器 E2E + **截图像素基线对比**；后端用例增至 130 |
| 文档 | 新增《需求规格说明书》（FR/BR/NFR 编号、数据字典、用例、需求追溯矩阵、任务书对照） |
| 运维脚本 | 新增 `scripts/mysql_check.py`：一条命令完成 MySQL 建表自检、`FOR UPDATE` 行锁验证与并发压测 |

## v2.1 主要改动

| 项 | 改动 |
| --- | --- |
| 鉴权 | 登录签发 Bearer 令牌（库里只存 SHA-256 摘要），接口不再接受 `user_id`，改 `user_id` 看别人预约/进管理接口的越权漏洞已修复 |
| 口令 | 明文口令改为 PBKDF2-HMAC-SHA256（20 万次迭代 + 每用户盐），存量明文启动时自动迁移 |
| 签到 | 新增签到时间窗口：开始前 30 分钟开放，超过「开始 + 15 分钟」判失效并记违规 |
| 后台 | 新增座位维护（开放/维护中切换）与用户概览（预约数、待处理违规），管理看板拆成四个页签 |
| 前端 | `app.js` 25 行压缩代码重写为 ES 模块（api / store / ui / charts / pages），新增自研 SVG 图表（折线、环形、排行），零第三方依赖 |

## v2.0 主要改动

| 项 | 改动 |
| --- | --- |
| 架构 | 425 行单文件拆分为 传输层 → 接口层 → 服务层 → 仓储层 → 数据底座，业务模块按「用户 / 预约 / 推荐 / 后台管理 / 数据统计」划分 |
| 数据库 | 新增 MySQL 8 支持（连接池、`InnoDB` 行锁、`DATE`/`TIME` 类型、utf8mb4），同时保留 SQLite 作为零依赖的本地演示模式，一行环境变量切换 |
| 违规预警 | 真正落地：超时未签到 → 预约失效 + 违规记录；超时未结束 → 自动结束 + 违规记录；后台线程定时扫描；违规累计到阈值限制预约 |
| 并发 | 创建预约改为「锁座位行 → 查冲突 → 插入」同一事务，杜绝并发抢座双订；HTTP 服务放大 listen backlog |

---

## 技术栈

- 后端：Python 3.10+ 标准库 `http.server`；MySQL 模式需要 `PyMySQL`
- 数据库：MySQL 8（生产/验收）/ SQLite（本地演示、单元测试）
- 鉴权：Bearer 令牌 + `sessions` 表，PBKDF2 口令哈希
- 实时：Server-Sent Events（进程内事件总线，零第三方依赖）
- 前端：原生 HTML / CSS / ES Module，图表为自研 SVG 组件（无 CDN、无构建）
- 测试：标准库 `unittest` + 自研压测脚本 + jsdom 冒烟 + Playwright E2E/截图基线
- 协作：Git，`dev` 开发、`main` 稳定

---

## 快速开始

### 方式一：SQLite（零依赖，最快跑通）

```powershell
python backend/server.py
```

打开 <http://127.0.0.1:8000>，首次启动自动建库到 `backend/data/study_room.db` 并写入演示数据。

### 方式二：MySQL（验收推荐）

1）起一个 MySQL（有 Docker 时一条命令，脚本会自动建表）：

```powershell
docker compose up -d
```

没有 Docker，用本机 MySQL 也行：

```powershell
pip install -r backend/requirements.txt
python scripts/init_mysql.py --host 127.0.0.1 --user root --password 你的密码
```

2）带环境变量启动后端：

```powershell
$env:DB_BACKEND="mysql"
$env:MYSQL_HOST="127.0.0.1"
$env:MYSQL_USER="root"
$env:MYSQL_PASSWORD="studyroom"
$env:MYSQL_DATABASE="campus_study_room"
python backend/server.py
```

> 完整可配置项见 `.env.example`。不指定 `DB_BACKEND` 时：配了 `MYSQL_HOST` 就走 MySQL，否则走 SQLite。

### 演示账号

| 类型 | 账号 | 密码 |
| --- | --- | --- |
| 学生 | `student001` | `123456` |
| 学生 | `student002` | `123456` |
| 管理员 | `admin` | `admin123` |

---

## 主要 API

除 `/api/health`、`/api/login` 外，所有接口都需要请求头 `Authorization: Bearer <token>`；身份由令牌解析，接口**不再接受 `user_id` 参数**。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查（公开），返回当前使用的库与规则参数 |
| POST | `/api/login` | 登录（公开），返回 `token` / `expires_at` / `user` |
| POST | `/api/logout` | 退出登录，令牌立即失效 |
| GET | `/api/me` | 当前登录用户，用于前端恢复会话 |
| GET | `/api/seats?date=&start=&end=` | 查询座位状态 |
| POST | `/api/reservations` | 创建预约（含冲突拦截、违规阈值校验） |
| GET | `/api/reservations` | 我的预约 |
| DELETE | `/api/reservations/{id}` | 取消预约 |
| POST | `/api/reservations/{id}/checkin` | 签到核销（限签到窗口内） |
| POST | `/api/reservations/{id}/checkout` | 结束自习 |
| GET | `/api/recommendations?date=&start=&end=` | 智能推荐（含时段热度上下文） |
| GET | `/api/events?token=` | SSE 实时事件流（预约/座位/违规变更） |
| GET | `/api/admin/stats` | 管理统计 |
| GET | `/api/admin/violations` | 违规预警列表 |
| POST | `/api/admin/violations/{id}/resolve` | 处理违规 |
| POST | `/api/admin/violations/scan` | 手动触发一次违规扫描（现场演示用） |
| GET | `/api/admin/users` | 用户概览（含预约数、待处理违规） |
| GET | `/api/admin/seats` | 座位列表（含维护状态） |
| POST | `/api/admin/seats/{id}/status` | 切换座位状态：`available` / `maintenance` |

统一返回结构：成功 `{"ok": true, ...}`，失败 `{"ok": false, "code": "...", "message": "..."}`。

## 实时推送

预约、取消、签到、结束、座位维护、违规扫描/处理都会通过 SSE 广播，前端按事件自动刷新，无需手动点"刷新"。

| 事件 | 触发 |
| --- | --- |
| `reservation.created` / `cancelled` | 创建 / 取消预约 |
| `reservation.checked_in` / `checked_out` | 签到 / 结束自习 |
| `seat.status` | 座位维护状态变化 |
| `violation.scanned` / `resolved` | 违规扫描 / 处理 |

事件总线为进程内实现（慢消费者丢最旧事件、连接数有上限）；多进程部署时把 `backend/events.py` 换成 Redis Pub/Sub 即可，上层接口不变。

---

## 违规占座预警规则

| 规则 | 触发条件 | 系统动作 | 违规类型 |
| --- | --- | --- | --- |
| 超时未签到 | 预约开始后超过 `NO_SHOW_GRACE_MINUTES`（默认 15）分钟仍未签到 | 预约置为 `expired`，记 1 条违规 | `no_show` |
| 超时占用 | 签到后超过结束时间 `OVERSTAY_GRACE_MINUTES`（默认 30）分钟仍未结束 | 预约置为 `completed`，记 1 条违规 | `overstay` |

- 扫描由后台线程按 `SWEEPER_INTERVAL`（默认 60s）执行，服务启动时也会先扫一遍；
- 扫描幂等：状态变更后不再命中待扫描集合，且 `violations(reservation_id, kind)` 有唯一键兜底；
- 用户近 `VIOLATION_WINDOW_DAYS`（默认 30）天内未处理违规达到 `VIOLATION_BLOCK_THRESHOLD`（默认 3）条时，禁止继续预约，管理员处理后可恢复。

## 签到时间窗口

| 时刻 | 结果 |
| --- | --- |
| 早于「开始 − `CHECKIN_EARLY_MINUTES`（默认 30）」 | 拒绝：还未到签到时间，并提示可签到时段 |
| 窗口内（开始前 30 分钟 ~ 开始后 15 分钟） | 签到成功，状态转 `checked_in` |
| 晚于「开始 + `NO_SHOW_GRACE_MINUTES`（默认 15）」 | 预约立即置 `expired` 并记 `no_show` 违规（与定时扫描同一套规则） |

设 `CHECKIN_ENFORCED=0` 可关闭窗口校验，便于课堂演示随时签到。

---

## 项目结构

```text
campus-ai-study-room/
├─ backend/
│  ├─ app.py                 # 装配入口（初始化库 → 迁移口令 → 装配服务 → 启动扫描线程 → 起服务）
│  ├─ server.py              # 兼容入口：python backend/server.py
│  ├─ config.py              # 环境变量配置
│  ├─ security.py            # 口令 PBKDF2 哈希、令牌生成与摘要
│  ├─ db.py                  # 数据底座：连接池 / 事务 / 加锁 / 方言适配
│  ├─ web.py                 # HTTP 传输层（Bearer 令牌、CORS、静态资源）
│  ├─ sweeper.py             # 违规扫描后台线程
│  ├─ events.py              # 事件总线（SSE 数据源）
│  ├─ api/router.py          # 路由表（令牌 → actor）
│  ├─ services/              # 业务层：auth / reservation / violation / recommendation / stats / admin / slot_rules
│  ├─ repositories/          # 仓储层：user / session / seat / reservation / violation / stats
│  └─ data/                  # 本地运行时数据库，不上传
├─ database/
│  ├─ mysql/                 # MySQL 建表 + 初始化数据
│  └─ sqlite/                # SQLite 建表 + 初始化数据
├─ frontend/
│  ├─ index.html / styles.css / favicon.svg
│  ├─ js/                    # ES 模块：api / realtime / store / ui / charts / pages / main
│  └─ tests/                 # jsdom 冒烟 + Playwright E2E（含截图基线）
├─ tests/                    # 单元测试 + 集成测试 + SSE 测试 + 并发测试
├─ scripts/
│  ├─ loadtest.py            # HTTP 层并发压力测试
│  ├─ mysql_check.py         # MySQL 实机自检与压测
│  ├─ seed_demo.py           # 演示数据
│  └─ init_mysql.py          # MySQL 一键初始化
├─ docs/
│  ├─ 需求规格/需求规格说明书.md
│  ├─ 环境搭建/本地MySQL环境.md
│  ├─ 系统设计/当前代码设计图稿.md
│  └─ 测试报告/测试报告-v2.2.md
├─ demo-data/                # 脱敏演示数据说明
├─ docker-compose.yml        # MySQL 8 一键启动
└─ .env.example              # 环境变量样例
```

---

## 测试

```powershell
# 后端全部用例（130 个：单元 66 / 集成 55 / SSE 6 / 并发 3）
python -m unittest discover -s tests -t . -v

# 并发压力测试（自动起临时服务，不影响开发数据）
python scripts/loadtest.py --users 30 --rounds 3 --reads 100

# 前端：先启动服务并灌演示数据
python backend/server.py
python scripts/seed_demo.py
cd frontend/tests && npm install
node ui-smoke.mjs                                     # jsdom 冒烟（25 项）
$env:BASE_URL="http://127.0.0.1:8000"; node ui-e2e.mjs  # 真实浏览器 + 截图基线（22 项）
```

当前结果：后端 130 个用例（SQLite 与 MySQL 双跑）、前端冒烟 25 项、E2E 22 项全部通过；截图基线与本次运行差异 0.000%。
详细数据见 [`docs/测试报告/测试报告-v2.2.md`](docs/测试报告/测试报告-v2.2.md)。

## MySQL 实机验证

本机已装 MySQL 8.0.40 便携版（`D:\MySQL`，端口 **3307**，root/studyroom），详见
[`docs/环境搭建/本地MySQL环境.md`](docs/环境搭建/本地MySQL环境.md)。

```powershell
D:\MySQL\start-mysql.bat                                          # 启动数据库
python scripts/init_mysql.py --port 3307 --password studyroom     # 建表 + 演示数据
python scripts/mysql_check.py --port 3307 --password studyroom    # 建表自检 + 行锁验证 + 压测
```

最近一次结果：

```text
[建表自检] 5 张表、29 个索引，reservations 引擎 InnoDB
[行锁验证] 两人同抢一个座位 → [201, 409]
[并发压测] 20 线程抢不同座位 → 20/20 成功，41.7 req/s
===== 3/3 项通过 =====
```

整套用例也能跑在 MySQL 上（130/130 通过）：把 `TEST_DB_BACKEND` 设为 `mysql`、`MYSQL_PORT` 设为 `3307`、
`MYSQL_PASSWORD` 设为 `studyroom`，再执行 `python -m unittest discover -s tests -t . -v` 即可。

> 实测写吞吐：SQLite 28~40 req/s，MySQL 283~374 req/s（InnoDB 行锁并行）。MySQL 上还额外发现了两个只在
> `REPEATABLE READ` 隔离级别下才出现的并发问题，修复记录见测试报告 D-18、D-19。

---

## 设计要点（答辩可用）

1. **分层与单向依赖**：传输层不认识 SQL，仓储层不认识 HTTP，业务规则集中在服务层，纯规则（时段校验、违规判定、推荐打分）抽成无副作用的纯函数，便于单测。
2. **并发不超卖**：创建预约在写事务内先锁座位行（MySQL `SELECT ... FOR UPDATE` / SQLite `BEGIN IMMEDIATE`）再查冲突再插入，把「检查-写入」的竞态关在锁内。
3. **双方言一份 SQL**：仓储层统一写 `?` 占位符，由 `Session` 翻译成 `%s`；结果集统一归一化（`datetime`/`date`/`Time`→字符串），上层无感知。
4. **违规判定与执行分离**：`decide()` 是纯函数（输入预约 + 当前时间 → 判定结果），`ViolationService.scan()` 只负责落库与状态流转，规则可单测、可调参。
5. **身份不可伪造**：令牌随机生成、库里只存摘要、有效期固定；接口不接收 `user_id`，越权只能靠拿到别人的令牌，而不是改一个数字。
6. **鉴权不抢写锁**：`authenticate()` 走只读事务，避免把每个请求都串行化在 SQLite 的写锁上（实测读吞吐从 37 提升到 271 req/s）。
7. **前端零依赖**：图表是自己写的 SVG 组件（`charts.js`），不依赖 CDN，离线答辩也能正常出图。
8. **实时但不阻塞**：SSE 发布走内存队列，队列满时丢最旧事件；订阅数有上限，慢客户端不会拖住请求线程。
9. **推荐可解释**：六个因子各自对应一句理由文案，答辩时能解释"为什么推荐这个座位"；热度只提示不打分，避免全局信息影响排序。

---

## 分支与提交约定

- `main`：稳定、可演示、可提交的版本。
- `dev`：日常开发和功能集成分支。
- 提交信息使用「模块：动作」格式：

```text
预约：增加时段冲突校验
架构：拆分为 controller-service-repository 三层
测试：增加并发抢座用例
```
