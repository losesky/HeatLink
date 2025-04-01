#!/usr/bin/env python3
"""
测试新闻源获取后是否正确将数据存入Redis缓存
"""

import os
import sys
import asyncio
import logging
from typing import Dict, List, Any, Optional

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from worker.cache import CacheManager
from worker.scheduler import AdaptiveScheduler
from worker.sources.provider import DefaultNewsSourceProvider
from worker.sources.base import NewsItemModel

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


class RedisIntegrationTester:
    """Redis 缓存集成测试类"""
    
    def __init__(self, redis_url: Optional[str] = None):
        """
        初始化测试器
        
        Args:
            redis_url: Redis URL
        """
        # 如果未提供 Redis URL，则使用环境变量
        if redis_url is None:
            redis_url = os.environ.get('REDIS_URL')
            if not redis_url:
                raise ValueError("Redis URL not provided and REDIS_URL environment variable not set")
        
        self.redis_url = redis_url
        logger.info(f"Using Redis URL: {self.redis_url}")
        
        # 创建源提供者
        self.source_provider = DefaultNewsSourceProvider()
        
        # 创建缓存管理器
        self.cache_manager = CacheManager(
            redis_url=redis_url,
            enable_memory_cache=True,
            verbose_logging=True
        )
        
        # 创建调度器
        self.scheduler = AdaptiveScheduler(
            source_provider=self.source_provider,
            cache_manager=self.cache_manager,
            enable_adaptive=False
        )
    
    async def initialize(self):
        """初始化测试环境"""
        # 初始化缓存管理器
        await self.cache_manager.initialize()
        
        # 初始化调度器
        await self.scheduler.initialize()
        
        logger.info("Test environment initialized")
    
    async def cleanup(self):
        """清理测试环境"""
        # 关闭缓存管理器
        await self.cache_manager.close()
        
        logger.info("Test environment cleaned up")
    
    async def test_news_source_cache(self, source_id: str) -> bool:
        """
        测试单个新闻源的缓存
        
        Args:
            source_id: 测试的新闻源ID
            
        Returns:
            测试是否成功
        """
        logger.info(f"Testing news source cache for: {source_id}")
        
        # 获取源
        source = self.scheduler.get_source(source_id)
        if not source:
            logger.error(f"Source {source_id} not found")
            return False
        
        # 清除该源的Redis缓存
        cache_key = f"source:{source_id}"
        await self.cache_manager.delete(cache_key)
        logger.info(f"Deleted existing cache for key: {cache_key}")
        
        # 验证缓存已清除
        cached_data = await self.cache_manager.get(cache_key)
        if cached_data:
            logger.error(f"Failed to clear cache for {source_id}")
            return False
        
        logger.info(f"Cache verification: no data in cache for {source_id}")
        
        # 抓取数据
        success = await self.scheduler.fetch_source(source_id, force=True)
        if not success:
            logger.error(f"Failed to fetch data from source: {source_id}")
            return False
        
        logger.info(f"Successfully fetched data from source: {source_id}")
        
        # 检查Redis缓存是否已更新
        cached_news = await self.cache_manager.get(cache_key)
        
        if not cached_news:
            logger.error(f"No data found in Redis cache for key: {cache_key}")
            return False
        
        logger.info(f"Found {len(cached_news)} items in Redis cache for {source_id}")
        
        # 验证缓存内容
        if not isinstance(cached_news, list):
            logger.error(f"Cache data is not a list: {type(cached_news)}")
            return False
        
        if len(cached_news) == 0:
            logger.warning(f"Cache list is empty for {source_id}")
        
        # 验证缓存中的新闻条目格式
        for item in cached_news[:3]:  # 只检查前3个
            if not isinstance(item, NewsItemModel):
                logger.error(f"Cache item is not a NewsItemModel: {type(item)}")
                return False
            
            if not hasattr(item, 'title') or not item.title:
                logger.error(f"Cache item missing title")
                return False
            
            logger.info(f"Sample cached news item: {item.title[:50]}...")
        
        return True
    
    async def run_tests(self, source_ids: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        运行测试
        
        Args:
            source_ids: 要测试的源ID列表，如果不提供，则测试所有源
            
        Returns:
            测试结果，键为源ID，值为测试是否成功
        """
        await self.initialize()
        
        try:
            # 如果未提供源ID列表，则获取所有源
            if not source_ids:
                sources = self.scheduler.get_all_sources()
                source_ids = [source.source_id for source in sources]
                logger.info(f"Testing all {len(source_ids)} sources")
            else:
                logger.info(f"Testing specified {len(source_ids)} sources")
            
            results = {}
            
            # 先测试36kr，这通常是比较稳定的源
            if "36kr" in source_ids:
                source_ids.remove("36kr")
                source_ids.insert(0, "36kr")
            
            # 测试每个源
            for source_id in source_ids:
                try:
                    result = await self.test_news_source_cache(source_id)
                    results[source_id] = result
                    logger.info(f"Test result for {source_id}: {'SUCCESS' if result else 'FAILED'}")
                except Exception as e:
                    logger.error(f"Error testing source {source_id}: {str(e)}")
                    results[source_id] = False
            
            # 打印总结
            success_count = sum(1 for result in results.values() if result)
            logger.info(f"Test summary: {success_count}/{len(results)} sources passed")
            
            for source_id, result in results.items():
                if not result:
                    logger.warning(f"Source failed: {source_id}")
            
            return results
        finally:
            await self.cleanup()


async def main():
    """主函数"""
    # 创建测试器
    redis_url = os.environ.get('REDIS_URL')
    if not redis_url:
        logger.error("REDIS_URL environment variable not set")
        return
    
    tester = RedisIntegrationTester(redis_url)
    
    # 解析命令行参数
    import argparse
    parser = argparse.ArgumentParser(description='Test Redis cache integration')
    parser.add_argument('--sources', type=str, help='Comma-separated list of source IDs to test')
    args = parser.parse_args()
    
    # 获取要测试的源ID列表
    source_ids = None
    if args.sources:
        source_ids = [s.strip() for s in args.sources.split(',')]
    
    # 运行测试
    results = await tester.run_tests(source_ids)
    
    # 确定退出代码
    success = all(results.values())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main()) 