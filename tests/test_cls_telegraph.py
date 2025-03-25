#!/usr/bin/env python3
"""
测试财联社电报页面抓取
修改了使用桌面版用户代理并支持移动版格式的解析
"""

import asyncio
import logging
import sys
import os
import json
from datetime import datetime

# 添加必要的路径以便能导入模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker.sources.sites.cls import CLSNewsSource

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("cls_telegraph_test.log")
    ]
)

logger = logging.getLogger("cls_telegraph_test")

async def test_telegraph_scraping():
    """测试财联社电报页面抓取"""
    logger.info("=" * 50)
    logger.info("开始测试财联社电报页面抓取")
    logger.info("=" * 50)
    
    # 创建CLSNewsSource实例
    source = CLSNewsSource(
        config={
            "use_selenium": False,  # 不使用Selenium
            "use_direct_api": False,  # 不使用API
            "use_scraping": True,  # 使用HTTP抓取
            "use_backup_api": False  # 不使用备用API
        }
    )
    
    try:
        # 直接调用_scrape_telegraph_page方法
        logger.info("调用_scrape_telegraph_page方法")
        telegraph_items = await source._scrape_telegraph_page()
        
        logger.info(f"成功获取到 {len(telegraph_items)} 条电报")
        
        # 打印前5条电报的详细信息
        logger.info("\n电报详细信息（前5条）:")
        for i, item in enumerate(telegraph_items[:5], 1):
            logger.info("-" * 40)
            logger.info(f"电报 #{i}")
            logger.info(f"ID: {item.id}")
            logger.info(f"标题: {item.title}")
            logger.info(f"内容: {item.content}")
            logger.info(f"URL: {item.url}")
            logger.info(f"发布时间: {item.published_at}")
            logger.info(f"来源: {item.extra.get('source', '未知')}")
            logger.info(f"抓取方式: {item.extra.get('fetched_by', '未知')}")
        
        # 检查不同来源的电报数量
        source_count = {}
        for item in telegraph_items:
            source_type = item.extra.get("fetched_by", "unknown")
            if source_type not in source_count:
                source_count[source_type] = 0
            source_count[source_type] += 1
        
        logger.info("\n按抓取方式分类统计:")
        for source_type, count in source_count.items():
            logger.info(f"{source_type}: {count}条")
        
        # 将结果保存到JSON文件中，方便查看
        result_file = f"cls_telegraph_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(
                [item.to_dict() for item in telegraph_items],
                f,
                ensure_ascii=False,
                indent=2
            )
        logger.info(f"\n结果已保存到文件: {result_file}")
        
        return telegraph_items
    except Exception as e:
        logger.error(f"抓取财联社电报时出错: {e}", exc_info=True)
        return []
    finally:
        # 确保关闭资源
        await source.close()

async def main():
    """主函数"""
    try:
        await test_telegraph_scraping()
    except Exception as e:
        logger.error(f"测试过程中发生异常: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main()) 