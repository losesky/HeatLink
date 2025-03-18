#!/usr/bin/env python3
"""
数据源测试脚本
=============

该脚本用于测试HeatLink项目中的所有新闻数据源适配器。它可以：
1. 测试单个或多个数据源
2. 测试所有可用的数据源
3. 生成测试报告
4. 自动处理Redis连接问题

使用方法:
    python test_sources_report.py [选项]

选项:
    --timeout SECONDS       设置单个数据源测试的超时时间（默认: 60秒）
    --max-concurrent N      设置最大并发测试数量（默认: 5）
    --sources SRC1 SRC2..   指定要测试的数据源列表（不指定则测试所有）
                            可以用空格分隔多个源，也可以用逗号分隔
    --output FILE           指定测试报告输出文件（默认: source_test_report.json）
    --force-disable-cache   强制禁用缓存，即使Redis可用

示例:
    # 测试所有数据源
    python test_sources_report.py
    
    # 仅测试特定数据源，用空格分隔
    python test_sources_report.py --sources zhihu weibo baidu
    
    # 仅测试特定数据源，用逗号分隔
    python test_sources_report.py --sources zhihu,weibo,baidu
    
    # 设置超时时间并指定输出文件
    python test_sources_report.py --timeout 30 --output my_report.json
    
    # 强制禁用缓存
    python test_sources_report.py --force-disable-cache

注意:
    - 该脚本会自动检测Redis服务器是否可用，并在需要时禁用缓存
    - 测试报告会显示每个数据源的测试结果，包括成功/失败状态、获取的数据项数量和耗时
    - 脚本同时会生成详细的JSON格式测试报告
"""

import sys
import os
import asyncio
import logging
import json
import time
import argparse
import socket
from datetime import datetime
from typing import Dict, List, Any, Optional

# 添加当前目录到 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 检查Redis服务器状态
def check_redis_server(host='127.0.0.1', port=6379, timeout=1):
    """检查Redis服务器是否可用"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False

# 根据Redis状态决定是否启用缓存
redis_available = check_redis_server()
if not redis_available:
    print("警告: Redis服务器不可用，已禁用缓存功能")
    os.environ['AIOCACHE_DISABLE'] = '1'

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
        if source is None:
            error_msg = f"Unknown source type: {source_type}"
            result["error"] = error_msg
            logger.error(error_msg)
            return result
            
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

async def test_all_sources(timeout: int = 60, max_concurrent: int = 5, sources_to_test: List[str] = None) -> Dict[str, Any]:
    """测试所有数据源"""
    start_time = datetime.now()
    
    # 获取所有数据源类型（改用get_available_sources替代create_default_sources）
    source_types = NewsSourceFactory.get_available_sources()
    
    # 如果指定了特定源，则只测试这些源
    if sources_to_test:
        source_types = [st for st in source_types if st in sources_to_test]
        logger.info(f"Testing {len(source_types)} specified sources: {', '.join(source_types)}")
    else:
        logger.info(f"Testing all {len(source_types)} sources")
    
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
            "total_time": f"{total_time:.2f}s",
            "redis_available": redis_available,
            "cache_enabled": not os.environ.get('AIOCACHE_DISABLE', '0') == '1',
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "tested_sources": source_types
        },
        "successful_sources": sorted(successful_sources, key=lambda x: x["source_type"]),
        "failed_sources": sorted(failed_sources, key=lambda x: x["source_type"])
    }

def print_report(results: Dict[str, Any]):
    """打印测试报告"""
    # 打印摘要
    summary = results["summary"]
    print("\n" + "=" * 80)
    print(f"数据源测试报告 - {summary['timestamp']}")
    print("=" * 80)
    print(f"总数据源数量: {summary['total_sources']}")
    print(f"成功数据源数量: {summary['successful_sources']}")
    print(f"失败数据源数量: {summary['failed_sources']}")
    print(f"成功率: {summary['success_rate']}")
    print(f"总耗时: {summary['total_time']}")
    print(f"Redis服务器可用: {'是' if summary['redis_available'] else '否'}")
    print(f"缓存功能启用: {'是' if summary['cache_enabled'] else '否'}")
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

def list_available_sources():
    """列出所有可用的数据源"""
    source_ids = sorted(NewsSourceFactory.get_available_sources())
    
    print("\n可用的数据源:")
    print("-" * 80)
    
    # 按列打印，每行4个
    col_width = 20
    num_cols = 4
    rows = [source_ids[i:i+num_cols] for i in range(0, len(source_ids), num_cols)]
    
    for row in rows:
        print(''.join(source.ljust(col_width) for source in row))
    
    print("\n要测试特定数据源，请使用 --sources 参数，例如:")
    print("python test_sources_report.py --sources zhihu weibo baidu")

async def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='测试数据源适配器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 测试所有数据源
  python test_sources_report.py
  
  # 仅测试特定数据源，用空格分隔
  python test_sources_report.py --sources zhihu weibo baidu
  
  # 仅测试特定数据源，用逗号分隔
  python test_sources_report.py --sources zhihu,weibo,baidu
  
  # 设置超时时间并指定输出文件
  python test_sources_report.py --timeout 30 --output my_report.json
  
  # 强制禁用缓存
  python test_sources_report.py --force-disable-cache
  
  # 列出所有可用的数据源
  python test_sources_report.py --list-sources
"""
    )
    parser.add_argument('--timeout', type=int, default=60, help='单个数据源测试超时时间（秒）')
    parser.add_argument('--max-concurrent', type=int, default=2, help='最大并发测试数量')
    parser.add_argument('--sources', nargs='+', help='要测试的特定数据源列表（空表示全部）。可以用空格分隔多个源，也可以用逗号分隔')
    parser.add_argument('--output', default='source_test_report.json', help='测试报告输出文件路径')
    parser.add_argument('--force-disable-cache', action='store_true', help='强制禁用缓存，即使Redis可用')
    parser.add_argument('--list-sources', action='store_true', help='列出所有可用的数据源ID')
    args = parser.parse_args()
    
    # 如果只是列出可用的数据源，则执行后退出
    if args.list_sources:
        list_available_sources()
        return
    
    # 如果指定了强制禁用缓存，则无视Redis状态
    if args.force_disable_cache and 'AIOCACHE_DISABLE' not in os.environ:
        print("已强制禁用缓存功能")
        os.environ['AIOCACHE_DISABLE'] = '1'
    
    # 处理逗号分隔的源列表
    sources_to_test = None
    if args.sources:
        # 如果用户提供了逗号分隔的列表，则分割它
        sources_to_test = []
        for source in args.sources:
            if ',' in source:
                # 分割逗号分隔的源，并添加到列表中
                sources_to_test.extend([s.strip() for s in source.split(',') if s.strip()])
            else:
                # 添加单个源
                sources_to_test.append(source.strip())
    
    print(f"开始测试数据源（超时：{args.timeout}秒，并发数：{args.max_concurrent}）...")
    if not redis_available or os.environ.get('AIOCACHE_DISABLE') == '1':
        print("注意：缓存功能已禁用，这可能会导致某些依赖缓存的数据源测试失败")
    
    # 测试所有或指定的数据源
    results = await test_all_sources(
        timeout=args.timeout, 
        max_concurrent=args.max_concurrent,
        sources_to_test=sources_to_test
    )
    print_report(results)
    
    # 保存结果到文件
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细报告已保存到 {args.output}")
    
    try:
        # 关闭http_client单例
        from worker.utils.http_client import http_client
        await http_client.close()
    except Exception as e:
        logger.warning(f"关闭http_client时发生错误: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 