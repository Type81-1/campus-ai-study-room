# 本地 MySQL 环境（D:\MySQL，便携版）

本机原来没有 MySQL 也没有 Docker，这里用官方 **Windows ZIP 便携版**装了一套，不写注册表、不装系统服务、不需要管理员权限，删目录即可卸载。

## 1. 基本情况

| 项 | 值 |
| --- | --- |
| 版本 | MySQL Community Server 8.0.40（winx64） |
| 安装目录 | `D:\MySQL`（约 1.2 GB，含安装包、程序、数据、日志） |
| 端口 | **3307**（避开可能被占用的 3306） |
| 账号 | `root` / `studyroom` |
| 数据库 | `campus_study_room`（utf8mb4 / utf8mb4_unicode_ci） |
| 字符集与时区 | `utf8mb4`，`+08:00` |
| 数据目录 | `D:\MySQL\data` |
| 日志 | `D:\MySQL\logs\mysql-error.log`、`mysql-slow.log`（超过 1 秒的慢查询） |

目录结构：

```text
D:\MySQL
├─ mysql-8.0.40-winx64\     程序目录（bin 里有 mysqld / mysql / mysqladmin）
├─ data\                    数据文件（InnoDB）
├─ logs\                    错误日志与慢查询日志
├─ download\                安装包 zip（可删，省 233 MB）
├─ my.ini                   配置（端口、字符集、时区、慢查询）
├─ start-mysql.bat          一键启动并打印版本
└─ stop-mysql.bat           一键优雅关闭
```

## 2. 启动与关闭

```bat
D:\MySQL\start-mysql.bat     :: 启动（窗口别关，关掉就等于停库）
D:\MySQL\stop-mysql.bat      :: 关闭
```

手动方式：

```powershell
D:\MySQL\mysql-8.0.40-winx64\bin\mysqld.exe --defaults-file=D:\MySQL\my.ini --console
D:\MySQL\mysql-8.0.40-winx64\bin\mysqladmin.exe -h127.0.0.1 -P3307 -uroot -pstudyroom shutdown
```

> 便携版没有注册系统服务，开机不会自启；需要常驻可以后续用 `mysqld --install` 注册服务（需管理员权限）。

## 3. 让项目连上这套 MySQL

```powershell
$env:DB_BACKEND="mysql"
$env:MYSQL_HOST="127.0.0.1"
$env:MYSQL_PORT="3307"
$env:MYSQL_USER="root"
$env:MYSQL_PASSWORD="studyroom"
$env:MYSQL_DATABASE="campus_study_room"
python backend/server.py
```

启动后访问 <http://127.0.0.1:8000>，`GET /api/health` 会显示 `mysql://root@127.0.0.1:3307/campus_study_room`。

## 4. 初始化与重置

```powershell
# 建表 + 演示数据（幂等，可重复执行）
python scripts/init_mysql.py --port 3307 --password studyroom

# 彻底重置（清空数据重新来）
D:\MySQL\mysql-8.0.40-winx64\bin\mysql.exe -h127.0.0.1 -P3307 -uroot -pstudyroom `
  -e "DROP DATABASE campus_study_room; CREATE DATABASE campus_study_room DEFAULT CHARACTER SET utf8mb4;"
python scripts/init_mysql.py --port 3307 --password studyroom
```

## 5. 实机验证

```powershell
python scripts/mysql_check.py --port 3307 --password studyroom
```

会依次检查：表/索引/存储引擎 → 两人抢同一座位（验证行锁）→ 20 线程并发压测。
最近一次执行结果：

```text
[连接成功] MySQL 8.0.40，数据库 campus_study_room
[建表自检] 表 5 个：reservations, seats, sessions, users, violations
          索引 29 个，reservations 引擎：InnoDB
[行锁验证] 两人同抢一个座位 → 状态码 [201, 409]
[并发压测] 20 线程抢不同座位 → 成功 20/20，吞吐 41.7 req/s
===== 结果：3/3 项通过 =====
```

## 6. 直接连库看看

```powershell
D:\MySQL\mysql-8.0.40-winx64\bin\mysql.exe -h127.0.0.1 -P3307 -uroot -pstudyroom campus_study_room
```

```sql
SHOW TABLES;
SELECT id, username, role, LEFT(password, 20) AS pwd_prefix FROM users;
SELECT r.id, s.code, r.reservation_date, r.start_time, r.end_time, r.status
FROM reservations r JOIN seats s ON s.id = r.seat_id ORDER BY r.id DESC LIMIT 10;
SELECT kind, message, status FROM violations ORDER BY id DESC LIMIT 5;
```

## 7. 卸载

先 `stop-mysql.bat` 关闭，然后直接删除 `D:\MySQL` 目录即可（已确认没有注册服务、没有写注册表）。
