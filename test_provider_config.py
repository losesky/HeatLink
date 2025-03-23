import sys
import os
import logging
import json

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath('.'))

def print_db_source_info():
    """打印数据库中的源信息"""
    try:
        import psycopg2
        # 连接数据库
        logger.info("连接到数据库...")
        conn = psycopg2.connect('postgresql://postgres:postgres@localhost:5432/heatlink_dev')
        cur = conn.cursor()
        
        # 获取所有源信息
        logger.info("获取所有源...")
        cur.execute("SELECT id, name, type, status, config FROM sources")
        rows = cur.fetchall()
        
        logger.info(f"数据库中共有 {len(rows)} 个源")
        
        # 获取CLS相关源的详细信息
        cur.execute("SELECT id, name, type, status, config FROM sources WHERE id LIKE 'cls%'")
        cls_sources = cur.fetchall()
        
        logger.info("\n=== CLS相关源信息 ===")
        for source in cls_sources:
            source_id, name, source_type, status, config = source
            logger.info(f"ID: {source_id}")
            logger.info(f"名称: {name}")
            logger.info(f"类型: {source_type}")
            logger.info(f"状态: {status}")
            logger.info(f"配置: {config}")
            logger.info("-" * 60)
        
        # 获取所有源ID列表
        source_ids = [row[0] for row in rows]
        logger.info(f"\n所有源ID: {source_ids}")
        
        conn.close()
    except Exception as e:
        logger.error(f"打印数据库源信息时出错: {str(e)}")

def test_provider_config():
    """测试新闻源提供者是否正确加载和应用数据库配置"""
    from worker.sources.provider import DefaultNewsSourceProvider
    from worker.sources.factory import NewsSourceFactory
    
    logger.info("开始测试DefaultNewsSourceProvider配置加载")
    
    # 打印数据库中的源信息
    print_db_source_info()
    
    # 打印可用的源类型
    available_sources = NewsSourceFactory.get_available_sources()
    logger.info(f"\n工厂支持的源类型: {available_sources}")
    
    # 创建源提供者
    provider = DefaultNewsSourceProvider()
    logger.info(f"创建了DefaultNewsSourceProvider，共有 {len(provider.sources)} 个源")
    
    # 打印所有创建的源ID
    created_sources = list(provider.sources.keys())
    logger.info(f"\n创建的源ID: {created_sources}")
    
    # 测试CLS源
    cls_source = provider.get_source("cls")
    if cls_source:
        logger.info(f"找到CLS源，配置如下:")
        logger.info(f"- config: {cls_source.config}")
        logger.info(f"- use_selenium: {getattr(cls_source, 'use_selenium', None)}")
        logger.info(f"- use_direct_api: {getattr(cls_source, 'use_direct_api', None)}")
        logger.info(f"- use_scraping: {getattr(cls_source, 'use_scraping', None)}")
        logger.info(f"- use_backup_api: {getattr(cls_source, 'use_backup_api', None)}")
    else:
        logger.error("未找到CLS源")
    
    # 测试CLS-article源
    cls_article_source = provider.get_source("cls-article")
    if cls_article_source:
        logger.info(f"找到CLS-article源，配置如下:")
        logger.info(f"- config: {cls_article_source.config}")
        logger.info(f"- use_selenium: {getattr(cls_article_source, 'use_selenium', None)}")
        logger.info(f"- use_direct_api: {getattr(cls_article_source, 'use_direct_api', None)}")
        logger.info(f"- use_scraping: {getattr(cls_article_source, 'use_scraping', None)}")
        logger.info(f"- use_backup_api: {getattr(cls_article_source, 'use_backup_api', None)}")
    else:
        logger.error("未找到CLS-article源")
    
    logger.info("测试完成")

if __name__ == "__main__":
    test_provider_config() 