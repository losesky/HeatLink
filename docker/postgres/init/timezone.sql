-- 设置数据库时区为东八区
ALTER DATABASE heatlink SET timezone TO 'Asia/Shanghai';
ALTER DATABASE postgres SET timezone TO 'Asia/Shanghai';

-- 为所有用户设置时区
ALTER ROLE postgres SET timezone TO 'Asia/Shanghai';

-- 设置当前会话时区并验证
SET timezone TO 'Asia/Shanghai';
-- 显示当前时区
SHOW TIMEZONE;

-- 记录设置时区的操作日志
CREATE TABLE IF NOT EXISTS system_log (
    id SERIAL PRIMARY KEY,
    operation TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

INSERT INTO system_log (operation) VALUES ('设置数据库时区为 Asia/Shanghai'); 