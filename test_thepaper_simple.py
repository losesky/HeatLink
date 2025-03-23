#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
简化测试脚本：测试修复后的澎湃新闻源
"""

import asyncio
import logging
from worker.sources.factory import NewsSourceFactory

# 设置日志 - 仅显示INFO级别及以上
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_thepaper")

# 设置其他模块的日志级别为WARNING，减少输出
logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("worker.sources.sites.thepaper_selenium").setLevel(logging.INFO)
logging.getLogger("worker.sources.config").setLevel(logging.WARNING)
logging.getLogger("worker.utils.cache_fix").setLevel(logging.WARNING)
logging.getLogger("worker.utils.http_client").setLevel(logging.WARNING)

async def test_thepaper():
    """测试澎湃新闻源"""
    logger.info("▶️ 开始测试澎湃新闻源适配器")
    
    # 创建源实例
    source = NewsSourceFactory.create_source('thepaper')
    logger.info(f"✅ 创建源: {source.source_id} (类型: {source.__class__.__name__})")
    
    try:
        # 获取新闻数据
        logger.info("🔍 正在获取新闻数据...")
        news_items = await source.fetch()
        
        # 打印结果
        logger.info(f"🎉 成功获取 {len(news_items)} 条新闻")
        
        # 打印前5条新闻
        logger.info("📰 获取到的新闻:")
        for i, item in enumerate(news_items[:5]):
            logger.info(f"   {i+1}. {item.title}")
        
        logger.info("✅ 测试完成！澎湃新闻源现在可以正常工作")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        # 确保关闭资源
        await source.close()
        logger.info("🧹 资源已清理")

if __name__ == "__main__":
    asyncio.run(test_thepaper()) 