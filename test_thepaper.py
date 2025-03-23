#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试脚本：测试修复后的澎湃新闻源
"""

import asyncio
import logging
from worker.sources.factory import NewsSourceFactory

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_thepaper")

async def test_thepaper():
    """测试澎湃新闻源"""
    logger.info("开始测试 ThePaperSeleniumSource 适配器")
    
    # 创建源实例
    source = NewsSourceFactory.create_source('thepaper')
    logger.info(f"创建源: {source.source_id} (类型: {source.__class__.__name__})")
    
    try:
        # 获取新闻数据
        logger.info("开始获取新闻数据...")
        news_items = await source.fetch()
        
        # 打印结果
        logger.info(f"成功获取 {len(news_items)} 条新闻")
        
        # 打印前3条新闻
        for i, item in enumerate(news_items[:3]):
            logger.info(f"新闻 {i+1}: {item.title} - {item.url}")
        
        logger.info("测试完成！")
        
    except Exception as e:
        logger.error(f"测试失败: {str(e)}", exc_info=True)
    finally:
        # 确保关闭资源
        await source.close()

if __name__ == "__main__":
    asyncio.run(test_thepaper()) 