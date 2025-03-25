#!/usr/bin/env python3
"""
检查数据源健康状态并修复财联社数据源
"""

import sys
import os
import json
import logging
import asyncio
from datetime import datetime, timedelta

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../.."))
sys.path.insert(0, project_root)

from sqlalchemy import text
from app.db.session import SessionLocal
from worker.sources.sites.cls import CLSNewsSource

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("sources_health_check.log")
    ]
)

logger = logging.getLogger("sources_health_check")

async def check_cls_source():
    """测试财联社源是否能正常抓取内容"""
    logger.info("开始测试财联社源是否能正常抓取内容")
    
    # 创建CLSNewsSource实例
    source = CLSNewsSource(
        config={
            "use_selenium": True,  # 启用Selenium进行测试
            "use_direct_api": False,
            "use_scraping": True,
            "use_backup_api": True
        }
    )
    
    try:
        # 测试电报页面抓取
        logger.info("测试电报页面抓取")
        telegraph_items = await source._scrape_telegraph_page()
        logger.info(f"电报页面抓取结果: {len(telegraph_items)} 条")
        
        # 测试热门文章抓取
        try:
            logger.info("测试热门文章抓取")
            article_items = await source._fetch_hot_articles()
            logger.info(f"热门文章抓取结果: {len(article_items)} 条")
        except Exception as e:
            logger.warning(f"热门文章抓取失败: {e}")
            article_items = []
        
        # 如果直接抓取失败，尝试使用Selenium
        if len(telegraph_items) == 0 and len(article_items) == 0:
            logger.info("常规抓取方法失败，尝试使用Selenium抓取")
            try:
                selenium_items = await source._scrape_with_selenium(source.CLS_TELEGRAPH_URL, "telegraph")
                logger.info(f"Selenium抓取结果: {len(selenium_items)} 条")
                telegraph_items = selenium_items
            except Exception as e:
                logger.error(f"Selenium抓取失败: {e}")
        
        # 判断源是否健康
        is_healthy = len(telegraph_items) > 0 or len(article_items) > 0
        
        if is_healthy:
            logger.info("财联社源健康，至少有一个抓取方法有效")
            return True
        else:
            logger.warning("财联社源不健康，所有抓取方法均无效")
            return False
    except Exception as e:
        logger.error(f"测试财联社源时出错: {e}", exc_info=True)
        return False
    finally:
        await source.close()

def update_source_status(source_id, new_status="ACTIVE"):
    """更新数据源状态"""
    logger.info(f"正在更新数据源 {source_id} 状态为 {new_status}")
    
    # 创建数据库会话
    db = SessionLocal()
    
    try:
        # 更新数据源状态和最后更新时间，同时清除错误信息
        db.execute(
            text("UPDATE sources SET status = :status, last_error = NULL, last_update = :now WHERE id = :id"),
            {"status": new_status, "id": source_id, "now": datetime.utcnow()}
        )
        db.commit()
        
        # 验证更新
        result = db.execute(
            text("SELECT id, name, status, last_error FROM sources WHERE id = :id"),
            {"id": source_id}
        ).fetchone()
        
        if result:
            logger.info(f"数据源 {result[0]} ({result[1]}) 状态已更新为 {result[2]}, 错误信息已清除")
            return True
        else:
            logger.error(f"未找到数据源 {source_id}")
            return False
    except Exception as e:
        logger.error(f"更新数据源状态时出错: {e}", exc_info=True)
        db.rollback()
        return False
    finally:
        db.close()

def check_all_sources_status():
    """检查所有数据源状态"""
    logger.info("检查所有数据源状态")
    
    # 创建数据库会话
    db = SessionLocal()
    
    try:
        # 查询所有数据源
        results = db.execute(
            text("SELECT id, name, status, last_error, updated_at FROM sources")
        ).fetchall()
        
        logger.info(f"发现 {len(results)} 个数据源")
        
        # 统计不同状态的数量
        status_count = {}
        error_sources = []
        
        for source in results:
            source_id, name, status, last_error, updated_at = source
            
            if status not in status_count:
                status_count[status] = 0
            status_count[status] += 1
            
            if status == "ERROR":
                error_sources.append((source_id, name, last_error, updated_at))
        
        logger.info("数据源状态统计:")
        for status, count in status_count.items():
            logger.info(f"  {status}: {count}个")
        
        if error_sources:
            logger.warning(f"发现 {len(error_sources)} 个处于ERROR状态的数据源:")
            for source_id, name, last_error, updated_at in error_sources:
                logger.warning(f"  {source_id} ({name}), 错误: {last_error or '无'}, 最后更新时间: {updated_at}")
            
        return error_sources
    except Exception as e:
        logger.error(f"检查数据源状态时出错: {e}", exc_info=True)
        return []
    finally:
        db.close()

async def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("开始数据源健康检查")
    logger.info(f"当前时间: {datetime.now()}")
    logger.info("=" * 50)
    
    # 检查所有数据源状态
    error_sources = check_all_sources_status()
    
    # 处理错误状态的数据源
    for source_id, name, last_error, _ in error_sources:
        if source_id.startswith("cls"):
            logger.info(f"检测到财联社相关源 {source_id} 处于错误状态，错误信息: {last_error or '无'}, 尝试修复")
            
            # 检查财联社源是否健康
            if source_id == "cls":
                is_healthy = await check_cls_source()
                if is_healthy:
                    update_source_status(source_id, "ACTIVE")
                else:
                    logger.warning(f"财联社源 {source_id} 仍然无法正常工作，保持错误状态")
            else:
                # 对于其他财联社相关源，直接设置为活跃状态
                update_source_status(source_id, "ACTIVE")
    
    logger.info("=" * 50)
    logger.info("数据源健康检查完成")
    logger.info("=" * 50)

if __name__ == "__main__":
    asyncio.run(main()) 