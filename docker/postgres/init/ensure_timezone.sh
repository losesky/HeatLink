#!/bin/bash
set -e

# 设置数据库时区为东八区（亚洲/上海）
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- 查看当前时区
    SHOW timezone;
    
    -- 设置当前会话时区
    SET timezone TO 'Asia/Shanghai';
    
    -- 为数据库永久设置时区
    ALTER DATABASE $POSTGRES_DB SET timezone TO 'Asia/Shanghai';
    
    -- 为 postgres 用户设置时区
    ALTER ROLE $POSTGRES_USER SET timezone TO 'Asia/Shanghai';
    
    -- 再次验证时区
    SHOW timezone;
    
    -- 显示当前时间戳（应该使用东八区）
    SELECT now();
EOSQL

echo "数据库时区设置完成：Asia/Shanghai（东八区）" 