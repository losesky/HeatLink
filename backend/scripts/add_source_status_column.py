#!/usr/bin/env python
"""
迁移脚本：向sources表添加status和last_update列
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 确保加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db.session import SessionLocal, engine
from app.models.source import SourceStatus

def add_missing_columns():
    """向sources表添加缺失的列"""
    try:
        with engine.connect() as conn:
            # 1. 检查status列是否存在
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='sources' AND column_name='status';
            """))
            
            if result.fetchone() is None:
                # 创建枚举类型（如果不存在）
                conn.execute(text("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sourcestatus') THEN
                            CREATE TYPE sourcestatus AS ENUM ('active', 'error', 'warning', 'inactive');
                        END IF;
                    END
                    $$;
                """))
                
                # 添加status列
                conn.execute(text("""
                    ALTER TABLE sources 
                    ADD COLUMN status sourcestatus DEFAULT 'inactive';
                """))
                
                # 设置所有active=true的源状态为'active'
                conn.execute(text("""
                    UPDATE sources 
                    SET status = 'active' 
                    WHERE active = true;
                """))
                
                # 设置错误次数大于0的源状态为'error'
                conn.execute(text("""
                    UPDATE sources 
                    SET status = 'error' 
                    WHERE error_count > 0;
                """))
                
                print("成功添加status列，并初始化了状态值")
            else:
                print("status列已存在，无需添加")
            
            # 2. 检查last_update列是否存在
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='sources' AND column_name='last_update';
            """))
            
            if result.fetchone() is None:
                # 添加last_update列
                conn.execute(text("""
                    ALTER TABLE sources 
                    ADD COLUMN last_update TIMESTAMP WITHOUT TIME ZONE;
                """))
                
                # 将last_updated的值复制到last_update（如果有）
                conn.execute(text("""
                    UPDATE sources 
                    SET last_update = last_updated 
                    WHERE last_updated IS NOT NULL;
                """))
                
                print("成功添加last_update列，并初始化了值")
            else:
                print("last_update列已存在，无需添加")
            
            # 提交事务
            conn.commit()
            
    except Exception as e:
        print(f"添加列时出错: {str(e)}")

if __name__ == "__main__":
    add_missing_columns() 