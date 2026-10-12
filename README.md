# 校园 AI 智能自习室预约系统

《软件工程基础》课程设计课题 1：校园 AI 智能自习室预约系统。

这是一个可以直接本地运行的课程设计原型，覆盖座位预约、冲突拦截、签到核销、智能推荐、后台统计和违规预警等核心流程。

## 当前实现

- 学生和管理员登录，按角色限制管理接口
- 24 个演示座位，支持按日期和时段查询状态
- 创建预约、取消预约、重复预约拦截、同座位时段冲突拦截
- 签到核销、结束自习和预约状态流转
- 根据靠窗、电源、安静区偏好生成可解释的座位推荐
- 管理员统计总预约数、今日预约、签到中数量和开放预警
- 热门座位、近 7 日预约趋势和违规预警记录
- 首次启动自动创建 SQLite 数据库和演示数据
- 已提供 API 集成测试

## 技术栈

- 后端：Python 3.10+ 标准库 `http.server`、`sqlite3`
- 前端：原生 HTML、CSS、JavaScript
- 数据库：SQLite
- 协作：Git，日常开发使用 `dev`，稳定版本使用 `main`

项目不依赖 Flask、Node.js 或其他第三方运行库。

## 本地启动

在项目根目录运行：

```powershell
python backend/server.py
```

启动后访问：<http://127.0.0.1:8000>

首次启动会自动生成：

```text
backend/data/study_room.db
```

该数据库属于本地运行数据，已经被 `.gitignore` 忽略，不会上传到仓库。

### 演示账号

| 类型 | 账号 | 密码 |
| --- | --- | --- |
| 学生 | `student001` | `123456` |
| 学生 | `student002` | `123456` |
| 管理员 | `admin` | `admin123` |

## 测试

使用 Python 标准库运行 API 集成测试：

```powershell
python -m unittest backend/test_server.py -v
```

测试覆盖登录、座位查询、预约冲突、签到、结束自习、推荐接口和管理员权限校验。

## 项目结构

```text
campus-ai-study-room/
├─ README.md
├─ backend/
│  ├─ server.py              # API、数据库初始化和静态文件服务
│  ├─ test_server.py         # API 集成测试
│  ├─ requirements.txt       # 依赖说明，目前只使用标准库
│  └─ data/                  # 本地运行时数据库，不上传
├─ frontend/
│  ├─ index.html             # 页面结构和登录界面
│  ├─ styles.css             # 响应式页面样式
│  └─ app.js                 # 页面交互和 API 调用
├─ database/                 # 数据库设计说明和脚本
├─ demo-data/                # 演示数据说明
└─ docs/                     # 需求、设计和测试文档
```

## 主要 API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/login` | 登录 |
| GET | `/api/seats` | 查询座位状态 |
| POST | `/api/reservations` | 创建预约 |
| GET | `/api/reservations?user_id=...` | 查询个人预约 |
| DELETE | `/api/reservations/{id}?user_id=...` | 取消预约 |
| POST | `/api/reservations/{id}/checkin` | 签到核销 |
| POST | `/api/reservations/{id}/checkout` | 结束自习 |
| GET | `/api/recommendations` | 获取座位推荐 |
| GET | `/api/admin/stats?user_id=...` | 获取管理统计 |
| GET | `/api/admin/violations?user_id=...` | 获取违规预警 |

## 小组成员

- 向柏梁：组长、需求与项目统筹
- 张宇：技术负责人、代码集成
- 谢龙汝：预约与座位模块
- 郑雨帆：用户、权限与后台管理
- 张天笑：签到核销与违规预警
- 翁可杰：智能推荐与数据统计
- 熊昊羽：测试负责人
- 伍世文：架构设计、文档与演示

## 分支与提交约定

- `main`：稳定、可演示、可提交的版本。
- `dev`：日常开发和功能集成分支。
- 新功能完成并自测后合并到 `dev`；验收前再将稳定版本合并到 `main`。
- 提交信息使用“模块：动作”的格式，例如：

```text
预约：增加时段冲突校验
文档：补充预约流程图
测试：增加重复签到用例
```

## 当前状态

核心预约原型已经完成并上传到 `dev` 分支。下一阶段可以补充 UML 图、需求规格说明、测试报告、部署截图，以及更严格的并发压力测试。
