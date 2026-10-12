# 后端

后端使用 Python 标准库 `http.server` 和 `sqlite3`，不需要安装 Flask。

## 启动

在项目根目录运行：

```powershell
python backend/server.py
```

打开 http://127.0.0.1:8000。首次启动会自动创建 `backend/data/study_room.db` 和演示数据。

演示账号：

- 学生：`student001` / `123456`
- 管理员：`admin` / `admin123`

## 测试

```powershell
python -m unittest backend/test_server.py -v
```
