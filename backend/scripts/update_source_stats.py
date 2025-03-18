#!/usr/bin/env python
"""
更新新闻源统计数据脚本

此脚本用于更新数据库中所有新闻源的统计数据，包括成功率、平均响应时间等。
可以定时运行此脚本来保持监控数据的更新。
"""
import sys
import os
import asyncio
import random
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 确保加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.source import Source
from app.crud.source_stats import update_source_status
from worker.sources.factory import NewsSourceFactory

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_adapter(source_id: str) -> dict:
    """测试适配器并返回性能指标"""
    try:
        # 创建适配器实例
        adapter = NewsSourceFactory.create_source(source_id)
        if not adapter:
            return {
                "success": False,
                "error_message": f"无法创建适配器 {source_id}",
                "response_time": 0,
                "total_requests": 0,
                "error_count": 1
            }
        
        # 记录开始时间
        start_time = time.time()
        
        # 测试获取新闻
        try:
            news_items = await adapter.fetch()
            success = True
            error_message = None
            error_count = 0
        except Exception as e:
            news_items = []
            success = False
            error_message = str(e)
            error_count = 1
        
        # 计算响应时间（毫秒）
        response_time = (time.time() - start_time) * 1000
        
        # 关闭适配器
        if hasattr(adapter, 'close') and callable(getattr(adapter, 'close')):
            await adapter.close()
        
        return {
            "success": success,
            "news_count": len(news_items),
            "response_time": response_time,
            "error_message": error_message,
            "total_requests": 1,
            "error_count": error_count
        }
    except Exception as e:
        logger.error(f"测试适配器 {source_id} 时出错: {str(e)}")
        return {
            "success": False,
            "error_message": str(e),
            "response_time": 0,
            "total_requests": 0,
            "error_count": 1
        }

async def update_stats_for_source(db: Session, source: Source) -> None:
    """为单个新闻源更新统计数据"""
    try:
        logger.info(f"正在更新新闻源 {source.id} 的统计数据...")
        
        # 测试适配器
        test_result = await test_adapter(source.id)
        
        # 获取现有的统计数据
        from app.crud.source_stats import get_latest_stats
        latest_stats = get_latest_stats(db, source.id)
        
        # 计算新的统计数据
        total_requests = (latest_stats.total_requests if latest_stats else 0) + test_result["total_requests"]
        error_count = (latest_stats.error_count if latest_stats else 0) + test_result["error_count"]
        
        # 计算成功率
        success_rate = (total_requests - error_count) / total_requests if total_requests > 0 else 0
        
        # 计算平均响应时间
        if latest_stats and latest_stats.total_requests > 0:
            # 加权平均，考虑历史数据
            prev_total = latest_stats.total_requests
            new_total = prev_total + test_result["total_requests"]
            avg_response_time = (
                (latest_stats.avg_response_time * prev_total) + 
                (test_result["response_time"] * test_result["total_requests"])
            ) / new_total
        else:
            # 没有历史数据，直接使用当前响应时间
            avg_response_time = test_result["response_time"]
        
        # 更新数据库
        update_source_status(
            db=db,
            source_id=source.id,
            success_rate=success_rate,
            avg_response_time=avg_response_time,
            total_requests=total_requests,
            error_count=error_count,
            last_error=test_result["error_message"] if not test_result["success"] else None
        )
        
        logger.info(f"已更新新闻源 {source.id} 的统计数据")
    except Exception as e:
        logger.error(f"更新新闻源 {source.id} 的统计数据时出错: {str(e)}")

async def update_all_sources(max_concurrent: int = 5) -> None:
    """更新所有新闻源的统计数据"""
    db = SessionLocal()
    try:
        # 获取所有活跃的新闻源
        sources = db.query(Source).filter(Source.active == True).all()
        logger.info(f"找到 {len(sources)} 个活跃的新闻源")
        
        # 使用信号量限制并发数量
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def update_with_semaphore(source):
            async with semaphore:
                return await update_stats_for_source(db, source)
        
        # 并发更新所有新闻源的统计数据
        tasks = [update_with_semaphore(source) for source in sources]
        await asyncio.gather(*tasks)
        
        logger.info("已完成所有新闻源的统计数据更新")
    except Exception as e:
        logger.error(f"更新新闻源统计数据时出错: {str(e)}")
    finally:
        db.close()

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="更新新闻源统计数据")
    parser.add_argument("--concurrent", type=int, default=5, help="最大并发数量")
    args = parser.parse_args()
    
    logger.info("开始更新新闻源统计数据...")
    
    try:
        # 运行异步任务
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(update_all_sources(max_concurrent=args.concurrent))
    except Exception as e:
        logger.error(f"更新过程中出错: {str(e)}")
        sys.exit(1)
    
    logger.info("所有新闻源统计数据更新完成")

if __name__ == "__main__":
    main() 