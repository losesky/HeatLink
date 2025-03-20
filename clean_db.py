#!/usr/bin/env python
"""
清理数据库中的重复记录
"""
import os
import sys
from sqlalchemy import create_engine, text

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 数据库连接信息
DB_URL = "postgresql://postgres:postgres@localhost:5432/heatlink_dev"

def clean_duplicate_sources():
    """清理数据库中的重复源记录"""
    try:
        # 创建数据库连接
        engine = create_engine(DB_URL)
        conn = engine.connect()
        
        try:
            # 开始事务
            trans = conn.begin()
            
            # 删除source_stats表中的记录
            result = conn.execute(text("DELETE FROM source_stats WHERE source_id = 'thepaper-selenium'"))
            print(f"从source_stats表中删除了 {result.rowcount} 条记录")
            
            # 删除news表中的记录
            result = conn.execute(text("DELETE FROM news WHERE source_id = 'thepaper-selenium'"))
            print(f"从news表中删除了 {result.rowcount} 条记录")
            
            # 删除source_aliases表中的记录
            result = conn.execute(text("DELETE FROM source_aliases WHERE source_id = 'thepaper-selenium'"))
            print(f"从source_aliases表中删除了 {result.rowcount} 条记录")
            
            # 删除sources表中的记录
            result = conn.execute(text("DELETE FROM sources WHERE id = 'thepaper-selenium'"))
            print(f"从sources表中删除了 {result.rowcount} 条记录")
            
            # 提交事务
            trans.commit()
            
            # 验证删除结果
            result = conn.execute(text("SELECT id, name, active FROM sources WHERE id LIKE '%thepaper%'"))
            remaining = list(result)
            print(f"剩余源记录:")
            for row in remaining:
                print(f"  {row.id}: {row.name} ({'活跃' if row.active else '非活跃'})")
            
            return True
        except Exception as e:
            print(f"清理过程中出错: {str(e)}")
            if trans and trans.is_active:
                trans.rollback()
            return False
        finally:
            conn.close()
            
    except Exception as e:
        print(f"连接数据库时出错: {str(e)}")
        return False

if __name__ == "__main__":
    print("开始清理数据库中的重复记录...")
    success = clean_duplicate_sources()
    if success:
        print("清理完成！")
    else:
        print("清理失败！")
        sys.exit(1) 