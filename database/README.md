# 数据库目录

按数据库类型分目录存放建表脚本与初始化数据，程序启动时会自动读取对应目录。

## mysql/

- `schema.sql`：MySQL 8 建表脚本（InnoDB / utf8mb4，含唯一键与索引）。
- `seed.sql`：脱敏演示账号与 24 个基础座位（`INSERT IGNORE`，可重复执行）。

```powershell
# 方式一：docker compose（首次启动自动执行上面两个脚本）
docker compose up -d

# 方式二：本机 MySQL 一键初始化
python scripts/init_mysql.py --host 127.0.0.1 --user root --password 你的密码
```

## sqlite/

- `schema.sql`：SQLite 建表脚本，字段语义与 MySQL 版一致。
- `seed.sql`：同样的演示数据（`INSERT OR IGNORE`）。

程序在 SQLite 模式下首次启动会自动建库到 `backend/data/study_room.db` 并写入演示数据，该文件不上传仓库。

## 表结构（5 张）

| 表 | 说明 |
| --- | --- |
| `users` | 账号、PBKDF2 口令哈希、角色、座位偏好 |
| `sessions` | 登录令牌的 SHA-256 摘要与过期时间（v2.1 新增） |
| `seats` | 座位编号、楼层、区域、属性、状态（`available` / `maintenance`） |
| `reservations` | 预约时段与状态（`booked` / `checked_in` / `completed` / `cancelled` / `expired`） |
| `violations` | 违规记录（`no_show` / `overstay`）与处理状态 |

## 存量库升级说明

`CREATE TABLE IF NOT EXISTS` 会自动补建 `sessions` 表，**无需手工迁移**。但 v2.1 把 `users.password` 加宽到 `VARCHAR(255)` 以容纳哈希串，若沿用 v2.0 建的 MySQL 库，需要执行一次：

```sql
ALTER TABLE users MODIFY COLUMN password VARCHAR(255) NOT NULL;
```

（SQLite 的 `TEXT` 类型不受影响，无需处理。启动时会自动把库里遗留的明文口令替换为哈希。）

## 两种方言的差异

| 项 | MySQL | SQLite |
| --- | --- | --- |
| 主键 | `INT UNSIGNED AUTO_INCREMENT` | `INTEGER PRIMARY KEY AUTOINCREMENT` |
| 日期时间 | `DATE` / `TIME` / `DATETIME` | `TEXT` |
| 静默插入 | `INSERT IGNORE` | `INSERT OR IGNORE` |
| 索引 | 建表内 `KEY` / `UNIQUE KEY` | 独立 `CREATE INDEX` |
| 并发 | `SELECT ... FOR UPDATE` 行锁 | `BEGIN IMMEDIATE` 库级写锁 |

上层代码只写 `?` 占位符与一套 SQL，由 `backend/db.py` 的 `Session` 完成方言翻译与结果归一化。
