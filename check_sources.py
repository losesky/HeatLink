#!/usr/bin/env python
"""
检查数据库中的新闻源记录
"""

import os
import sys
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("check_sources")

def check_sources():
    """列出并检查数据库中的所有源记录"""
    try:
        from backend.app.core.config import settings
        # 创建数据库连接
        engine = create_engine(settings.DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        logger.info(f"正在连接数据库: {settings.DATABASE_URL}")
        
        try:
            # 列出所有源记录
            result = db.execute(text("SELECT id, name, active, update_interval FROM sources ORDER BY id"))
            sources = []
            active_count = 0
            inactive_count = 0
            
            for row in result:
                source_id, name, active, update_interval = row
                sources.append({
                    "id": source_id,
                    "name": name,
                    "active": active,
                    "update_interval": update_interval
                })
                
                if active:
                    active_count += 1
                else:
                    inactive_count += 1
            
            logger.info(f"数据库中总共有 {len(sources)} 个源记录")
            logger.info(f"  活跃源: {active_count} 个")
            logger.info(f"  非活跃源: {inactive_count} 个")
            
            # 列出所有源的ID和名称
            logger.info("所有源列表:")
            for source in sources:
                status = "活跃" if source["active"] else "非活跃"
                logger.info(f"  {source['id']} ({source['name']}): {status}")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"检查源时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False
    
    return True

if __name__ == "__main__":
    logger.info("开始检查数据库中的新闻源记录...")
    success = check_sources()
    if success:
        logger.info("检查完成")
    else:
        logger.error("检查失败")
        sys.exit(1) 