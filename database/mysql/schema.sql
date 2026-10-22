-- 校园 AI 智能自习室预约系统 —— MySQL 8 建表脚本
-- 字符集统一 utf8mb4，存储引擎 InnoDB（需要事务与行锁）
-- 执行方式：mysql -u root -p < database/mysql/schema.sql（库需先创建）

CREATE TABLE IF NOT EXISTS users (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    username    VARCHAR(64)  NOT NULL,
    password    VARCHAR(128) NOT NULL,
    name        VARCHAR(64)  NOT NULL,
    role        VARCHAR(16)  NOT NULL,
    preferences VARCHAR(255) NOT NULL DEFAULT '{}',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_users_username (username),
    CONSTRAINT chk_users_role CHECK (role IN ('student', 'admin'))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS seats (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    code        VARCHAR(16)  NOT NULL,
    floor       TINYINT      NOT NULL,
    zone        VARCHAR(32)  NOT NULL,
    seat_type   VARCHAR(16)  NOT NULL DEFAULT 'standard',
    near_window TINYINT(1)   NOT NULL DEFAULT 0,
    power       TINYINT(1)   NOT NULL DEFAULT 0,
    status      VARCHAR(16)  NOT NULL DEFAULT 'available',
    PRIMARY KEY (id),
    UNIQUE KEY uk_seats_code (code),
    KEY idx_seats_floor (floor, id),
    CONSTRAINT chk_seats_status CHECK (status IN ('available', 'maintenance'))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS reservations (
    id               INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id          INT UNSIGNED NOT NULL,
    seat_id          INT UNSIGNED NOT NULL,
    reservation_date DATE         NOT NULL,
    start_time       TIME         NOT NULL,
    end_time         TIME         NOT NULL,
    status           VARCHAR(16)  NOT NULL DEFAULT 'booked',
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checkin_at       DATETIME     NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_reservation_user_slot (user_id, reservation_date, start_time, end_time),
    KEY idx_reservation_slot (seat_id, reservation_date, start_time, end_time),
    KEY idx_reservation_user (user_id, reservation_date),
    KEY idx_reservation_status (status, reservation_date),
    CONSTRAINT fk_reservation_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_reservation_seat FOREIGN KEY (seat_id) REFERENCES seats (id),
    CONSTRAINT chk_reservation_status CHECK (status IN ('booked', 'checked_in', 'completed', 'cancelled', 'expired'))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS violations (
    id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id        INT UNSIGNED NOT NULL,
    reservation_id INT UNSIGNED NULL,
    kind           VARCHAR(32)  NOT NULL,
    message        VARCHAR(255) NOT NULL,
    status         VARCHAR(16)  NOT NULL DEFAULT 'open',
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_violation_reservation_kind (reservation_id, kind),
    KEY idx_violation_user (user_id, status, created_at),
    CONSTRAINT fk_violation_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_violation_reservation FOREIGN KEY (reservation_id) REFERENCES reservations (id),
    CONSTRAINT chk_violation_status CHECK (status IN ('open', 'resolved'))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
