#!/usr/bin/env python
"""
检查并清理数据库中过时的新闻源记录
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
logger = logging.getLogger("clean_db_sources")

# 需要检查的过时源ID
OBSOLETE_SOURCES = [
    "bbc_news",  # 已被 bbc_world 替代
    "hacker_news"  # 已被 hackernews 替代
]

def clean_obsolete_sources():
    """检查并清理数据库中过时的新闻源记录"""
    try:
        from backend.app.core.config import settings
        # 创建数据库连接
        engine = create_engine(settings.DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        logger.info(f"正在连接数据库: {settings.DATABASE_URL}")
        
        try:
            # 列出所有源记录
            result = db.execute(text("SELECT id, name, active FROM sources"))
            sources = {}
            active_count = 0
            inactive_count = 0
            
            for row in result:
                source_id, name, active = row
                sources[source_id] = {
                    "name": name,
                    "active": active
                }
                
                if active:
                    active_count += 1
                else:
                    inactive_count += 1
            
            logger.info(f"数据库中有 {len(sources)} 个源记录")
            logger.info(f"  活跃源: {active_count} 个")
            logger.info(f"  非活跃源: {inactive_count} 个")
            
            # 检查过时的源
            for source_id in OBSOLETE_SOURCES:
                if source_id in sources:
                    source = sources[source_id]
                    if source["active"]:
                        logger.warning(f"过时源 {source_id} ({source['name']}) 仍被标记为活跃")
                        
                        # 如果需要将过时源标记为非活跃，可以取消下面的注释
                        # db.execute(
                        #     text("UPDATE sources SET active = false WHERE id = :source_id"),
                        #     {"source_id": source_id}
                        # )
                        # db.commit()
                        # logger.info(f"已将源 {source_id} 标记为非活跃")
                    else:
                        logger.info(f"过时源 {source_id} ({source['name']}) 已被标记为非活跃")
                else:
                    logger.info(f"源 {source_id} 不存在")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"检查过时源时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False
    
    return True

if __name__ == "__main__":
    logger.info("开始检查数据库中的过时新闻源记录...")
    success = clean_obsolete_sources()
    if success:
        logger.info("检查完成")
    else:
        logger.error("检查失败")
        sys.exit(1) 