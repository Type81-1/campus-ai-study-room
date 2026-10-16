# 数据库目录

保存数据库建表脚本、初始化数据脚本和数据库设计说明。

## 文件说明

- `schema.sql`：与 `backend/server.py` 中 `init_db()` 保持一致的 SQLite 建表脚本。
- `seed.sql`：脱敏演示账号和 24 个基础座位的初始化数据。
- `backend/data/study_room.db`：程序运行时自动生成的本地数据库，不上传仓库。

## 手动初始化

```powershell
sqlite3 backend/data/study_room.db ".read database/schema.sql"
sqlite3 backend/data/study_room.db ".read database/seed.sql"
```

通常不需要手动执行，直接运行 `python backend/server.py` 即可自动初始化。
