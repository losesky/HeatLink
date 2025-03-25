#!/usr/bin/env python3
"""
测试财联社源的抓取功能
"""

import sys
import os
import asyncio
import logging
from datetime import datetime

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("test_cls_source")

async def test_cls_source():
    """测试财联社源的抓取功能"""
    try:
        from worker.sources.factory import NewsSourceFactory
        from worker.sources.provider import DefaultNewsSourceProvider
        
        logger.info("开始测试财联社源")
        
        # 初始化源提供者
        provider = DefaultNewsSourceProvider()
        
        # 获取CLS源
        cls_source = provider.get_source("cls")
        if not cls_source:
            logger.error("未找到CLS源，测试失败")
            return
        
        logger.info(f"成功获取CLS源: {cls_source.source_id}, {cls_source.name}")
        logger.info(f"配置信息: use_selenium={cls_source.use_selenium}, use_direct_api={cls_source.use_direct_api}, use_scraping={cls_source.use_scraping}")
        
        # 获取新闻
        logger.info("开始抓取新闻...")
        start_time = datetime.now()
        try:
            news_items = await cls_source.fetch()
            end_time = datetime.now()
            
            if news_items:
                logger.info(f"成功获取 {len(news_items)} 条新闻，耗时: {(end_time - start_time).total_seconds():.2f}秒")
                
                # 输出第一条新闻的内容
                if len(news_items) > 0:
                    first_item = news_items[0]
                    logger.info(f"第一条新闻示例: ")
                    logger.info(f"  ID: {first_item.id}")
                    logger.info(f"  标题: {first_item.title}")
                    logger.info(f"  链接: {first_item.url}")
                    logger.info(f"  摘要: {first_item.summary[:100] + '...' if len(first_item.summary) > 100 else first_item.summary}")
                    logger.info(f"  发布时间: {first_item.published_at}")
            else:
                logger.warning("没有获取到新闻")
        except Exception as e:
            logger.error(f"抓取新闻时出错: {str(e)}", exc_info=True)
        
        # 获取cls-article源
        cls_article_source = provider.get_source("cls-article")
        if not cls_article_source:
            logger.error("未找到CLS-article源，测试失败")
            return
        
        logger.info(f"成功获取CLS-article源: {cls_article_source.source_id}, {cls_article_source.name}")
        logger.info(f"配置信息: use_selenium={cls_article_source.use_selenium}, use_direct_api={cls_article_source.use_direct_api}, use_scraping={cls_article_source.use_scraping}")
        
        # 获取新闻
        logger.info("开始抓取文章...")
        start_time = datetime.now()
        try:
            news_items = await cls_article_source.fetch()
            end_time = datetime.now()
            
            if news_items:
                logger.info(f"成功获取 {len(news_items)} 条文章，耗时: {(end_time - start_time).total_seconds():.2f}秒")
                
                # 输出第一条新闻的内容
                if len(news_items) > 0:
                    first_item = news_items[0]
                    logger.info(f"第一条文章示例: ")
                    logger.info(f"  ID: {first_item.id}")
                    logger.info(f"  标题: {first_item.title}")
                    logger.info(f"  链接: {first_item.url}")
                    logger.info(f"  摘要: {first_item.summary[:100] + '...' if len(first_item.summary) > 100 else first_item.summary}")
                    logger.info(f"  发布时间: {first_item.published_at}")
            else:
                logger.warning("没有获取到文章")
        except Exception as e:
            logger.error(f"抓取文章时出错: {str(e)}", exc_info=True)
        
    except Exception as e:
        logger.error(f"测试过程中出错: {str(e)}", exc_info=True)

def main():
    """主函数"""
    asyncio.run(test_cls_source())

if __name__ == "__main__":
    main() 