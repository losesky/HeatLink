#!/usr/bin/env python3
"""
检查CLS相关源在数据库中的配置
"""

from app.db.session import SessionLocal
from sqlalchemy import text

def main():
    # 创建数据库会话
    db = SessionLocal()
    
    try:
        # 查询所有cls相关源
        query = text("SELECT id, name, type, status, config FROM sources WHERE id LIKE 'cls%'")
        sources = db.execute(query).fetchall()
        
        print("财联社相关源的信息:")
        print("-" * 60)
        
        for source in sources:
            print(f"ID: {source[0]}")
            print(f"名称: {source[1]}")
            print(f"类型: {source[2]}")
            print(f"状态: {source[3]}")
            print(f"配置: {source[4]}")
            print("-" * 60)
            
    finally:
        # 关闭会话
        db.close()
        
if __name__ == "__main__":
    main() 