#!/usr/bin/env python3
"""
测试财联社新闻源适配器
"""

import asyncio
import logging
import traceback
import sys
from worker.sources.sites.cls import CLSNewsSource

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,  # 使用DEBUG级别以获取更多信息
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 获取logger
logger = logging.getLogger("cls_test")

async def test_cls_adapter():
    """测试财联社适配器"""
    try:
        logger.info("开始测试财联社适配器...")
        source = CLSNewsSource()
        
        # 测试直接API调用
        try:
            logger.info("测试获取财联社电报...")
            telegraph_items = await source._fetch_telegraph()
            logger.info(f"获取到 {len(telegraph_items)} 条财联社电报")
        except Exception as e:
            logger.error(f"获取财联社电报失败: {e}")
            logger.debug(traceback.format_exc())
        
        try:
            logger.info("测试获取热门文章...")
            hot_items = await source._fetch_hot_articles()
            logger.info(f"获取到 {len(hot_items)} 条热门文章")
        except Exception as e:
            logger.error(f"获取热门文章失败: {e}")
            logger.debug(traceback.format_exc())
        
        try:
            logger.info("测试获取环球市场情报...")
            global_items = await source._fetch_global_market()
            logger.info(f"获取到 {len(global_items)} 条环球市场情报")
        except Exception as e:
            logger.error(f"获取环球市场情报失败: {e}")
            logger.debug(traceback.format_exc())
        
        # 测试网页爬取
        try:
            logger.info("测试爬取网页...")
            scrape_items = await source._scrape_cls_website()
            logger.info(f"爬取到 {len(scrape_items)} 条新闻")
        except Exception as e:
            logger.error(f"爬取网页失败: {e}")
            logger.debug(traceback.format_exc())
        
        # 测试第三方API
        for api_url in source.BACKUP_API_URLS:
            try:
                logger.info(f"测试第三方API: {api_url}")
                backup_items = await source._fetch_from_backup_api(api_url)
                logger.info(f"从 {api_url} 获取到 {len(backup_items)} 条新闻")
            except Exception as e:
                logger.error(f"从 {api_url} 获取数据失败: {e}")
                logger.debug(traceback.format_exc())
        
        # 完整测试
        logger.info("开始完整获取测试...")
        items = await source.fetch()
        
        logger.info(f"\n获取到 {len(items)} 条新闻")
        logger.info("-" * 50)
        
        # 按来源分类
        source_groups = {}
        for item in items:
            source_name = item.extra.get("source", "未知来源")
            if source_name not in source_groups:
                source_groups[source_name] = []
            source_groups[source_name].append(item)
        
        # 打印各来源的新闻数量
        logger.info("\n各来源新闻数量:")
        for source_name, source_items in source_groups.items():
            logger.info(f"{source_name}: {len(source_items)}条")
        
        # 打印每个来源的前3条新闻
        for source_name, source_items in source_groups.items():
            logger.info("\n" + "=" * 30)
            logger.info(f"{source_name} 前3条新闻:")
            logger.info("=" * 30)
            
            for i, item in enumerate(source_items[:3], 1):
                logger.info(f"{i}. {item.title}")
                logger.info(f"   URL: {item.url}")
                if item.published_at:
                    logger.info(f"   发布时间: {item.published_at}")
                if item.summary:
                    logger.info(f"   摘要: {item.summary[:100]}...")
                logger.info("-" * 30)
    
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")
        logger.debug(traceback.format_exc())
        
if __name__ == "__main__":
    try:
        asyncio.run(test_cls_adapter())
    except KeyboardInterrupt:
        logger.info("测试被用户中断")
    except Exception as e:
        logger.error(f"未捕获的异常: {e}")
        logger.debug(traceback.format_exc())
        sys.exit(1) 