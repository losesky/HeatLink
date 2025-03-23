#!/usr/bin/env python3
"""
激活财联社相关源
"""

from app.db.session import SessionLocal
from sqlalchemy import text

def main():
    """主函数"""
    # 创建数据库会话
    db = SessionLocal()
    
    try:
        # 将财联社相关源状态设置为ACTIVE
        db.execute(
            text("UPDATE sources SET status = 'ACTIVE' WHERE id IN ('cls', 'cls-article')")
        )
        db.commit()
        print('已将财联社源状态设置为ACTIVE')
        
        # 查询财联社相关源状态
        result = db.execute(
            text("SELECT id, name, status, config FROM sources WHERE id IN ('cls', 'cls-article')")
        ).fetchall()
        
        print("财联社相关源信息:")
        for row in result:
            print(f"ID: {row[0]}")
            print(f"名称: {row[1]}")
            print(f"状态: {row[2]}")
            print(f"配置: {row[3]}")
            print("-" * 60)
    finally:
        db.close()

if __name__ == "__main__":
    main() 