#!/usr/bin/env python
"""
修复脚本：重新创建sourcestatus枚举类型，使用大写值
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 确保加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db.session import engine
from app.models.source import SourceStatus

def fix_source_status_enum():
    """修复sourcestatus枚举类型，确保使用大写值"""
    try:
        with engine.connect() as conn:
            # 1. 先将现有的status列值保存到临时列
            conn.execute(text("""
                ALTER TABLE sources ADD COLUMN temp_status VARCHAR(50);
                UPDATE sources SET temp_status = status::text;
            """))
            conn.commit()
            
            # 2. 删除status列
            conn.execute(text("""
                ALTER TABLE sources DROP COLUMN status;
            """))
            conn.commit()
            
            # 3. 删除枚举类型（先处理可能的依赖关系）
            conn.execute(text("""
                DROP TYPE IF EXISTS sourcestatus CASCADE;
            """))
            conn.commit()
            
            # 4. 创建新的枚举类型，使用大写值
            # 注意：SourceStatus枚举成员使用的是大写名称（如ACTIVE），值是小写（如'active'）
            # 但我们需要创建PostgreSQL枚举时使用大写值，以匹配SQLAlchemy的期望
            conn.execute(text("""
                CREATE TYPE sourcestatus AS ENUM ('ACTIVE', 'ERROR', 'WARNING', 'INACTIVE');
            """))
            conn.commit()
            
            # 5. 添加新的status列
            conn.execute(text("""
                ALTER TABLE sources ADD COLUMN status sourcestatus DEFAULT 'INACTIVE';
            """))
            conn.commit()
            
            # 6. 将临时列的值转换回status列（需要转换为大写）
            conn.execute(text("""
                UPDATE sources SET status = UPPER(temp_status)::sourcestatus WHERE temp_status IS NOT NULL;
                ALTER TABLE sources DROP COLUMN temp_status;
            """))
            conn.commit()
            
            print("成功修复了sourcestatus枚举类型（使用大写值）")
    except Exception as e:
        print(f"修复sourcestatus枚举类型时出错: {str(e)}")

if __name__ == "__main__":
    fix_source_status_enum() 