#!/usr/bin/env python3
import sys
import os
import asyncio
import logging
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

# 添加当前目录到 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from worker.sources.factory import NewsSourceFactory
from worker.sources.base import NewsSource

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("source_tester")

async def close_source(source):
    """关闭数据源，释放资源"""
    if source is None:
        return
    
    try:
        # 调用 close 方法
        if hasattr(source, 'close'):
            try:
                await source.close()
                return  # 如果成功关闭，直接返回
            except Exception as e:
                logger.warning(f"Error calling close() method: {str(e)}")
        
        # 尝试关闭 http_client
        if hasattr(source, '_http_client') and source._http_client is not None:
            # 直接访问 _http_client 属性，避免调用可能是协程的 http_client 属性
            if hasattr(source._http_client, 'close'):
                await source._http_client.close()
        
        # 尝试关闭 aiohttp 会话
        import aiohttp
        import inspect
        for attr_name in dir(source):
            if attr_name.startswith('_'):
                continue
                
            try:
                # 跳过属性访问器和协程
                attr = getattr(source.__class__, attr_name, None)
                if attr and (inspect.iscoroutine(attr) or inspect.isawaitable(attr) or 
                           inspect.iscoroutinefunction(attr) or isinstance(attr, property)):
                    continue
                
                # 获取实例属性
                attr = getattr(source, attr_name)
                
                # 关闭 aiohttp 会话
                if isinstance(attr, aiohttp.ClientSession) and not attr.closed:
                    await attr.close()
            except (AttributeError, TypeError):
                # 跳过协程属性或其他无法直接访问的属性
                pass
    except Exception as e:
        logger.warning(f"Error closing source: {str(e)}")

async def test_source(source_type: str, timeout: int = 60) -> Dict[str, Any]:
    """测试单个数据源"""
    result = {
        "source_type": source_type,
        "success": False,
        "error": None,
        "items_count": 0,
        "elapsed_time": 0
    }
    
    logger.info(f"Testing source: {source_type}")
    
    # 创建数据源
    source = None
    try:
        source = NewsSourceFactory.create_source(source_type)
        
        # 获取数据
        start_time = time.time()
        try:
            # 使用 asyncio.wait_for 添加超时机制
            fetch_task = asyncio.create_task(source.fetch())
            news_items = await asyncio.wait_for(fetch_task, timeout=timeout)
            elapsed_time = time.time() - start_time
            
            # 记录结果
            result["success"] = True
            result["items_count"] = len(news_items)
            result["elapsed_time"] = elapsed_time
            
            logger.info(f"Fetch successful: {len(news_items)} items in {elapsed_time:.2f}s")
        except asyncio.TimeoutError:
            elapsed_time = time.time() - start_time
            error_msg = f"Timeout after {elapsed_time:.2f}s"
            result["error"] = error_msg
            logger.error(error_msg)
        except Exception as e:
            elapsed_time = time.time() - start_time
            error_msg = f"Error fetching data: {str(e)}"
            result["error"] = error_msg
            logger.error(error_msg)
    except Exception as e:
        error_msg = f"Error creating source: {str(e)}"
        result["error"] = error_msg
        logger.error(error_msg)
    finally:
        # 关闭数据源
        if source:
            await close_source(source)
    
    return result

async def test_all_sources(timeout: int = 60, max_concurrent: int = 5) -> Dict[str, Any]:
    """测试所有数据源"""
    start_time = datetime.now()
    
    # 获取所有默认数据源
    sources = NewsSourceFactory.create_default_sources()
    source_types = [source.source_id for source in sources]
    
    # 关闭所有数据源
    for source in sources:
        await close_source(source)
    
    logger.info(f"Testing {len(source_types)} sources...")
    
    # 创建信号量限制并发数
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def test_with_semaphore(source_type: str) -> Dict[str, Any]:
        async with semaphore:
            result = await test_source(source_type, timeout=timeout)
            return result
    
    # 创建所有测试任务
    tasks = [test_with_semaphore(source_type) for source_type in source_types]
    
    # 执行所有任务
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理结果
    successful_sources = []
    failed_sources = []
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Task error for {source_types[i]}: {str(result)}")
            failed_sources.append({
                "source_type": source_types[i],
                "error": str(result)
            })
            continue
        
        if result["success"]:
            successful_sources.append({
                "source_type": result["source_type"],
                "items_count": result["items_count"],
                "elapsed_time": result["elapsed_time"]
            })
        else:
            failed_sources.append({
                "source_type": result["source_type"],
                "error": result["error"]
            })
    
    end_time = datetime.now()
    total_time = (end_time - start_time).total_seconds()
    
    return {
        "summary": {
            "total_sources": len(source_types),
            "successful_sources": len(successful_sources),
            "failed_sources": len(failed_sources),
            "success_rate": f"{len(successful_sources) / len(source_types) * 100:.1f}%",
            "total_time": f"{total_time:.2f}s"
        },
        "successful_sources": sorted(successful_sources, key=lambda x: x["source_type"]),
        "failed_sources": sorted(failed_sources, key=lambda x: x["source_type"])
    }

def print_report(results: Dict[str, Any]):
    """打印测试报告"""
    # 打印摘要
    summary = results["summary"]
    print("\n" + "=" * 80)
    print(f"数据源测试报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print(f"总数据源数量: {summary['total_sources']}")
    print(f"成功数据源数量: {summary['successful_sources']}")
    print(f"失败数据源数量: {summary['failed_sources']}")
    print(f"成功率: {summary['success_rate']}")
    print(f"总耗时: {summary['total_time']}")
    print("-" * 80)
    
    # 打印成功的数据源
    print("\n成功的数据源:")
    print("-" * 80)
    print(f"{'数据源':<20} {'数据项数量':<12} {'耗时(秒)':<10}")
    print("-" * 80)
    for source in results["successful_sources"]:
        print(f"{source['source_type']:<20} {source['items_count']:<12} {source['elapsed_time']:<10.2f}")
    
    # 打印失败的数据源
    print("\n失败的数据源:")
    print("-" * 80)
    if not results["failed_sources"]:
        print("没有失败的数据源")
    else:
        print(f"{'数据源':<20} {'错误':<60}")
        print("-" * 80)
        for source in results["failed_sources"]:
            error = source['error']
            if len(error) > 60:
                error = error[:57] + "..."
            print(f"{source['source_type']:<20} {error}")
    
    print("\n" + "=" * 80)

async def main():
    """主函数"""
    print("开始测试所有数据源，这可能需要几分钟时间...")
    results = await test_all_sources(timeout=60, max_concurrent=5)
    print_report(results)
    
    # 保存结果到文件
    with open("source_test_report.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细报告已保存到 source_test_report.json")
    
    # 关闭http_client单例
    from worker.utils.http_client import http_client
    await http_client.close()

if __name__ == "__main__":
    asyncio.run(main()) 