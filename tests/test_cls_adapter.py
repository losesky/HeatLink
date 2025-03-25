import asyncio
import logging
import json
from worker.sources.sites.cls import CLSNewsSource

# 设置日志级别
logging.basicConfig(level=logging.DEBUG)  # 设置为DEBUG以获取更多日志信息

async def main():
    # 创建配置，禁用Selenium使用
    config = {
        "use_selenium": False,  # 禁用Selenium
        "use_direct_api": True,  # 启用直接API访问
        "use_scraping": True,    # 启用HTTP爬取
        "use_backup_api": True,  # 启用备用API
    }
    
    print("\n" + "="*80)
    print("测试财联社新闻源 - 配置信息")
    print("="*80)
    print("使用的配置:")
    print(json.dumps(config, indent=2))
    print("="*80 + "\n")
    
    # 创建源实例，使用配置
    source = CLSNewsSource(config=config)
    
    print("\n" + "="*80)
    print("Source对象的配置:")
    print(f"- use_selenium: {source.use_selenium}")
    print(f"- use_direct_api: {source.use_direct_api}")
    print(f"- use_scraping: {source.use_scraping}")
    print(f"- use_backup_api: {source.use_backup_api}")
    print("\nConfig字典中的值:")
    print(f"- config: {source.config}")
    print(f"- config类型: {type(source.config)}")
    print(f"- config['use_selenium']: {source.config.get('use_selenium')}")
    print(f"- config['use_direct_api']: {source.config.get('use_direct_api')}")
    print(f"- config['use_scraping']: {source.config.get('use_scraping')}")
    print(f"- config['use_backup_api']: {source.config.get('use_backup_api')}")
    
    # 检查父类的config
    from worker.sources.rest_api import RESTNewsSource
    if isinstance(source, RESTNewsSource):
        print("\n是RESTNewsSource的实例")
    else:
        print("\n不是RESTNewsSource的实例")
    print("="*80 + "\n")
    
    try:
        print("\n正在获取财联社新闻...")
        news = await source.fetch()
        print(f"获取到 {len(news)} 条新闻")
        
        # 按来源分类
        source_groups = {}
        for item in news:
            source_name = item.extra.get("source", "未知来源")
            if source_name not in source_groups:
                source_groups[source_name] = []
            source_groups[source_name].append(item)
        
        # 打印各来源的新闻数量
        print("\n各来源新闻数量:")
        for source_name, items in source_groups.items():
            print(f"{source_name}: {len(items)}条")
        
        # 打印每个来源的前2条新闻
        for source_name, items in source_groups.items():
            print(f"\n--- {source_name} 前2条新闻 ---")
            for i, item in enumerate(items[:2], 1):
                print(f"{i}. {item.title}")
                print(f"   URL: {item.url}")
                if item.published_at:
                    print(f"   发布时间: {item.published_at}")
                print(f"   摘要: {(item.summary or '')[:100]}...")
                print("-" * 50)
    finally:
        await source.close()

if __name__ == "__main__":
    asyncio.run(main()) 