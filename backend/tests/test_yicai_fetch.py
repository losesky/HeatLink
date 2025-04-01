#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试脚本：测试第一财经新闻适配器的数据获取功能
"""

import sys
import os
import asyncio
import logging
import datetime
from pathlib import Path

# 添加项目根目录到Python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

from worker.sources.factory import NewsSourceFactory

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_yicai_fetch")

async def test_yicai_fetch():
    """测试第一财经新闻源的数据获取功能"""
    logger.info("开始测试 YiCaiNewsSource 适配器的数据获取功能")
    
    # 创建源实例
    source = NewsSourceFactory.create_source('yicai')
    if not source:
        logger.error("创建第一财经新闻源失败")
        return
        
    logger.info(f"创建源: {source.source_id} (类型: {source.__class__.__name__})")
    
    try:
        # 获取新闻数据
        logger.info("开始获取新闻数据...")
        start_time = datetime.datetime.now()
        news_items = await source.fetch()
        end_time = datetime.datetime.now()
        
        # 计算获取数据所需时间
        fetch_time = (end_time - start_time).total_seconds()
        
        # 打印结果
        logger.info(f"成功获取 {len(news_items)} 条新闻，用时: {fetch_time:.2f} 秒")
        
        # 打印新闻分类统计
        news_types = {}
        for item in news_items:
            item_type = item.extra.get('type', 'unknown')
            news_types[item_type] = news_types.get(item_type, 0) + 1
        
        logger.info("新闻分类统计:")
        for type_name, count in news_types.items():
            logger.info(f"  {type_name}: {count} 条")
        
        # 打印前5条新闻详情
        logger.info("\n前5条新闻详情:")
        for i, item in enumerate(news_items[:5]):
            logger.info(f"新闻 {i+1}:")
            logger.info(f"  标题: {item.title}")
            logger.info(f"  链接: {item.url}")
            logger.info(f"  发布时间: {item.published_at}")
            logger.info(f"  类型: {item.extra.get('type', 'unknown')}")
            logger.info(f"  数据来源: {item.extra.get('source_from', 'unknown')}")
            if item.summary:
                logger.info(f"  摘要: {item.summary[:100]}..." if len(item.summary) > 100 else f"  摘要: {item.summary}")
            logger.info("")
        
        logger.info("测试完成！")
        
    except Exception as e:
        logger.error(f"测试失败: {str(e)}", exc_info=True)
    finally:
        # 确保关闭资源
        await source.close()

if __name__ == "__main__":
    asyncio.run(test_yicai_fetch()) 