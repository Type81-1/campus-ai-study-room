-- 校园 AI 智能自习室预约系统数据库结构
-- 当前后端使用 SQLite；如迁移到 MySQL，可将 AUTOINCREMENT 改为 AUTO_INCREMENT，CURRENT_TIMESTAMP 保持不变。

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('student', 'admin')),
    preferences TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS seats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    floor INTEGER NOT NULL,
    zone TEXT NOT NULL,
    seat_type TEXT NOT NULL DEFAULT 'standard',
    near_window INTEGER NOT NULL DEFAULT 0,
    power INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'available'
);

CREATE TABLE IF NOT EXISTS reservations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    seat_id INTEGER NOT NULL REFERENCES seats(id),
    reservation_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'booked'
        CHECK (status IN ('booked', 'checked_in', 'completed', 'cancelled', 'expired')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checkin_at TEXT,
    UNIQUE (user_id, reservation_date, start_time, end_time)
);

CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    reservation_id INTEGER REFERENCES reservations(id),
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'resolved')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reservation_slot
    ON reservations (seat_id, reservation_date, start_time, end_time);

CREATE INDEX IF NOT EXISTS idx_reservation_user
    ON reservations (user_id, reservation_date);
