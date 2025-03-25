#!/usr/bin/env python
"""测试ThePaper数据源适配器的简化输出"""
import asyncio
import sys
import logging
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 配置根日志记录
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# 导入ThePaperSeleniumSource
from worker.sources.sites.thepaper_selenium import ThePaperSeleniumSource

async def main():
    print("\n===== 开始测试ThePaperSeleniumSource简化输出 =====")
    source = ThePaperSeleniumSource()
    print(f"初始化ThePaperSeleniumSource: {source.name}")
    
    try:
        print("\n开始获取新闻数据...")
        news_items = await source.fetch()
        print(f"\n获取到 {len(news_items)} 条新闻")
        
        # 打印前3条新闻作为示例
        print("\n示例新闻条目:")
        for i, item in enumerate(news_items[:3], 1):
            print(f"\n新闻 {i}:")
            # 直接访问对象属性而不是用get方法
            print(f"  标题: {item.title if hasattr(item, 'title') else '无标题'}")
            print(f"  URL: {item.url if hasattr(item, 'url') else '无URL'}")
            # 尝试多种方式访问类别
            category = None
            if hasattr(item, 'category'):
                category = item.category
            elif hasattr(item, 'tags') and item.tags:
                category = ', '.join(item.tags)
            print(f"  分类: {category or '未分类'}")
            
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n测试完成")

if __name__ == "__main__":
    asyncio.run(main()) 