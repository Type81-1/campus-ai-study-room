-- 校园 AI 智能自习室预约系统 —— SQLite 建表脚本（本地演示 / 单元测试使用）
-- 表结构与 database/mysql/schema.sql 一一对应

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL UNIQUE,
    password    TEXT NOT NULL,
    name        TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('student', 'admin')),
    preferences TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash   TEXT NOT NULL UNIQUE,
    user_id      INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    expires_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    floor       INTEGER NOT NULL,
    zone        TEXT NOT NULL,
    seat_type   TEXT NOT NULL DEFAULT 'standard',
    near_window INTEGER NOT NULL DEFAULT 0,
    power       INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'maintenance'))
);

CREATE TABLE IF NOT EXISTS reservations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES users (id),
    seat_id          INTEGER NOT NULL REFERENCES seats (id),
    reservation_date TEXT NOT NULL,
    start_time       TEXT NOT NULL,
    end_time         TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'booked'
                     CHECK (status IN ('booked', 'checked_in', 'completed', 'cancelled', 'expired')),
    created_at       TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    checkin_at       TEXT,
    UNIQUE (user_id, reservation_date, start_time, end_time)
);

CREATE TABLE IF NOT EXISTS violations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users (id),
    reservation_id INTEGER REFERENCES reservations (id),
    kind           TEXT NOT NULL,
    message        TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (reservation_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_reservation_slot ON reservations (seat_id, reservation_date, start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_reservation_user ON reservations (user_id, reservation_date);
CREATE INDEX IF NOT EXISTS idx_reservation_status ON reservations (status, reservation_date);
CREATE INDEX IF NOT EXISTS idx_violation_user ON violations (user_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_seats_floor ON seats (floor, id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions (expires_at);
