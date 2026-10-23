# 校园 AI 智能自习室预约系统

《软件工程基础》课程设计 选题 1：校园 AI 智能自习室预约系统。

覆盖座位预约、时段锁定、违规占座预警、空闲座位智能推荐、签到核销、后台权限管理与预约数据统计，采用**分层架构 + MySQL + 令牌鉴权** 实现，并配有单元测试、集成测试、并发压力测试与前端无头冒烟测试。

---

## 本版（v2.1）主要改动

| 项 | 改动 |
| --- | --- |
| 鉴权 | 登录签发 Bearer 令牌（库里只存 SHA-256 摘要），接口不再接受 `user_id`，改 `user_id` 看别人预约/进管理接口的越权漏洞已修复 |
| 口令 | 明文口令改为 PBKDF2-HMAC-SHA256（20 万次迭代 + 每用户盐），存量明文启动时自动迁移 |
| 签到 | 新增签到时间窗口：开始前 30 分钟开放，超过「开始 + 15 分钟」判失效并记违规 |
| 后台 | 新增座位维护（开放/维护中切换）与用户概览（预约数、待处理违规），管理看板拆成四个页签 |
| 前端 | `app.js` 25 行压缩代码重写为 ES 模块（api / store / ui / charts / pages），新增自研 SVG 图表（折线、环形、排行），零第三方依赖 |
| 测试 | 单元 49 + 集成 53 + 并发 3 = **105 个用例**，外加 25 项前端无头冒烟检查 |

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
- 前端：原生 HTML / CSS / ES Module，图表为自研 SVG 组件（无 CDN、无构建）
- 测试：标准库 `unittest` + 自研并发压测脚本 + jsdom 前端冒烟脚本
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
| GET | `/api/recommendations?date=&start=&end=` | 智能推荐 |
| GET | `/api/admin/stats` | 管理统计 |
| GET | `/api/admin/violations` | 违规预警列表 |
| POST | `/api/admin/violations/{id}/resolve` | 处理违规 |
| POST | `/api/admin/violations/scan` | 手动触发一次违规扫描（现场演示用） |
| GET | `/api/admin/users` | 用户概览（含预约数、待处理违规） |
| GET | `/api/admin/seats` | 座位列表（含维护状态） |
| POST | `/api/admin/seats/{id}/status` | 切换座位状态：`available` / `maintenance` |

统一返回结构：成功 `{"ok": true, ...}`，失败 `{"ok": false, "code": "...", "message": "..."}`。

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
│  ├─ api/router.py          # 路由表（令牌 → actor）
│  ├─ services/              # 业务层：auth / reservation / violation / recommendation / stats / admin / slot_rules
│  ├─ repositories/          # 仓储层：user / session / seat / reservation / violation / stats
│  └─ data/                  # 本地运行时数据库，不上传
├─ database/
│  ├─ mysql/                 # MySQL 建表 + 初始化数据
│  └─ sqlite/                # SQLite 建表 + 初始化数据
├─ frontend/
│  ├─ index.html / styles.css
│  └─ js/                    # ES 模块：api / store / ui / charts / pages / main
├─ tests/                    # 单元测试 + 集成测试 + 并发测试
├─ scripts/
│  ├─ loadtest.py            # HTTP 层并发压力测试
│  └─ init_mysql.py          # MySQL 一键初始化
├─ docs/
│  ├─ 系统设计/当前代码设计图稿.md
│  └─ 测试报告/测试报告-v2.1.md
├─ demo-data/                # 脱敏演示数据说明
├─ docker-compose.yml        # MySQL 8 一键启动
└─ .env.example              # 环境变量样例
```

---

## 测试

```powershell
# 全部用例（105 个）
python -m unittest discover -s tests -t . -v

# 并发压力测试（自动起临时服务，不影响开发数据）
python scripts/loadtest.py --users 30 --rounds 3 --reads 100
```

当前结果：单元测试 49、集成测试 53、并发测试 3，全部通过；另有 25 项前端无头冒烟检查（jsdom）通过。
详细数据见 [`docs/测试报告/测试报告-v2.1.md`](docs/测试报告/测试报告-v2.1.md)。

---

## 设计要点（答辩可用）

1. **分层与单向依赖**：传输层不认识 SQL，仓储层不认识 HTTP，业务规则集中在服务层，纯规则（时段校验、违规判定、推荐打分）抽成无副作用的纯函数，便于单测。
2. **并发不超卖**：创建预约在写事务内先锁座位行（MySQL `SELECT ... FOR UPDATE` / SQLite `BEGIN IMMEDIATE`）再查冲突再插入，把「检查-写入」的竞态关在锁内。
3. **双方言一份 SQL**：仓储层统一写 `?` 占位符，由 `Session` 翻译成 `%s`；结果集统一归一化（`datetime`/`date`/`Time`→字符串），上层无感知。
4. **违规判定与执行分离**：`decide()` 是纯函数（输入预约 + 当前时间 → 判定结果），`ViolationService.scan()` 只负责落库与状态流转，规则可单测、可调参。
5. **身份不可伪造**：令牌随机生成、库里只存摘要、有效期固定；接口不接收 `user_id`，越权只能靠拿到别人的令牌，而不是改一个数字。
6. **鉴权不抢写锁**：`authenticate()` 走只读事务，避免把每个请求都串行化在 SQLite 的写锁上（实测读吞吐从 37 提升到 271 req/s）。
7. **前端零依赖**：图表是自己写的 SVG 组件（`charts.js`），不依赖 CDN，离线答辩也能正常出图。

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
