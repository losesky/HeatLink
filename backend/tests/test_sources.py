import os
import sys
import json
import time
import asyncio
import logging
import argparse
from typing import Dict, List, Any, Optional

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 导入工厂类
from worker.sources.factory import NewsSourceFactory

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("test_sources")


async def test_source(source_type: str, **kwargs) -> Dict[str, Any]:
    """测试单个数据源"""
    result = {
        "source_type": source_type,
        "success": False,
        "error": None,
        "items_count": 0,
        "elapsed_time": 0,
        "items": []
    }
    
    logger.info(f"Testing source: {source_type}")
    
    # 创建数据源
    source = NewsSourceFactory.create_source(source_type, **kwargs)
    if not source:
        result["error"] = f"Failed to create source: {source_type}"
        logger.error(result["error"])
        return result
    
    # 获取数据
    start_time = time.time()
    try:
        items = await source.fetch()
        elapsed_time = time.time() - start_time
        result["elapsed_time"] = elapsed_time
        
        if items:
            result["success"] = True
            result["items_count"] = len(items)
            result["items"] = [item.to_dict() for item in items[:5]]  # 只保留前5条用于展示
            
            logger.info(f"Successfully fetched {len(items)} items from {source_type} in {elapsed_time:.2f}s")
            for i, item in enumerate(items[:3]):  # 只打印前3条
                logger.info(f"  {i+1}. {item.title}")
        else:
            result["error"] = "No items fetched"
            logger.warning(f"No items fetched from {source_type}")
    except Exception as e:
        elapsed_time = time.time() - start_time
        result["elapsed_time"] = elapsed_time
        result["error"] = str(e)
        logger.error(f"Error fetching from {source_type}: {str(e)}")
    
    return result


async def test_all_sources() -> Dict[str, Any]:
    """测试所有数据源"""
    results = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "sources": []
    }
    
    # 获取所有数据源
    sources = NewsSourceFactory.create_default_sources()
    results["total"] = len(sources)
    
    logger.info(f"Testing {len(sources)} sources...")
    
    # 逐个测试
    for source in sources:
        source_type = source.source_id
        result = await test_source(source_type)
        results["sources"].append(result)
        
        if result["success"]:
            results["success"] += 1
        else:
            results["failed"] += 1
    
    logger.info(f"Test completed: {results['success']}/{results['total']} sources succeeded")
    
    return results


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Test news sources")
    parser.add_argument("--source", type=str, help="Test specific source")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()
    
    if args.source:
        # 测试单个数据源
        result = await test_source(args.source)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # 测试所有数据源
        results = await test_all_sources()
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main()) 