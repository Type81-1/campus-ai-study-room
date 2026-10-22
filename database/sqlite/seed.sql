-- 脱敏演示账号与基础座位数据（SQLite）
-- 使用 INSERT OR IGNORE，重复执行不会报错

INSERT OR IGNORE INTO users (username, password, name, role, preferences) VALUES
('student001', '123456', '演示学生', 'student', '{"window": true, "power": true}'),
('student002', '123456', '测试同学', 'student', '{"window": false, "power": true}'),
('admin', 'admin123', '系统管理员', 'admin', '{}');

INSERT OR IGNORE INTO seats (code, floor, zone, seat_type, near_window, power, status) VALUES
('1F-01', 1, '靠窗区', 'standard', 1, 1, 'available'),
('1F-02', 1, '靠窗区', 'standard', 1, 1, 'available'),
('1F-03', 1, '靠窗区', 'standard', 1, 0, 'available'),
('1F-04', 1, '靠窗区', 'standard', 1, 1, 'available'),
('1F-05', 1, '安静区', 'standard', 0, 1, 'available'),
('1F-06', 1, '安静区', 'standard', 0, 1, 'available'),
('1F-07', 1, '安静区', 'standard', 0, 0, 'available'),
('1F-08', 1, '安静区', 'standard', 0, 1, 'available'),
('2F-01', 2, '靠窗区', 'standard', 1, 1, 'available'),
('2F-02', 2, '靠窗区', 'standard', 1, 1, 'available'),
('2F-03', 2, '靠窗区', 'standard', 1, 0, 'available'),
('2F-04', 2, '靠窗区', 'standard', 1, 1, 'available'),
('2F-05', 2, '安静区', 'standard', 0, 1, 'available'),
('2F-06', 2, '安静区', 'standard', 0, 1, 'available'),
('2F-07', 2, '安静区', 'standard', 0, 0, 'available'),
('2F-08', 2, '安静区', 'standard', 0, 1, 'available'),
('3F-01', 3, '靠窗区', 'standard', 1, 1, 'available'),
('3F-02', 3, '靠窗区', 'standard', 1, 1, 'available'),
('3F-03', 3, '靠窗区', 'standard', 1, 0, 'available'),
('3F-04', 3, '靠窗区', 'standard', 1, 1, 'available'),
('3F-05', 3, '安静区', 'standard', 0, 1, 'available'),
('3F-06', 3, '安静区', 'standard', 0, 1, 'available'),
('3F-07', 3, '安静区', 'standard', 0, 0, 'available'),
('3F-08', 3, '安静区', 'standard', 0, 1, 'available');
