#!/usr/bin/env python3
"""
专门测试 Kr36NewsSource 与 Redis 缓存的集成情况
"""

import os
import sys
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from worker.cache import CacheManager
from worker.scheduler import AdaptiveScheduler
from worker.sources.provider import DefaultNewsSourceProvider
from worker.sources.sites.kr36 import Kr36NewsSource

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


class Kr36RedisCacheTester:
    """Kr36NewsSource Redis 缓存集成测试类"""
    
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
    
    async def test_kr36_cache(self) -> bool:
        """
        测试36kr新闻源缓存
        
        Returns:
            测试是否成功
        """
        source_id = "36kr"
        logger.info(f"Testing Kr36NewsSource cache integration")
        
        # 获取源
        source = self.scheduler.get_source(source_id)
        if not source:
            logger.error(f"Source {source_id} not found")
            return False
        
        if not isinstance(source, Kr36NewsSource):
            logger.error(f"Source {source_id} is not a Kr36NewsSource, but {type(source)}")
            return False
        
        logger.info(f"Found source: {source.source_id} ({source.name})")
        logger.info(f"Source cache settings: TTL={source.cache_ttl}s, update_interval={source.update_interval}s")
        
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
        
        # 获取内部缓存状态
        in_memory_cache_before = getattr(source, '_cached_news_items', [])
        in_memory_cache_time_before = getattr(source, '_last_cache_update', 0)
        
        logger.info(f"In-memory cache before: {len(in_memory_cache_before)} items, last update: {in_memory_cache_time_before}")
        
        # 抓取数据
        success = await self.scheduler.fetch_source(source_id, force=True)
        if not success:
            logger.error(f"Failed to fetch data from source: {source_id}")
            return False
        
        logger.info(f"Successfully fetched data from source: {source_id}")
        
        # 获取更新后的内部缓存状态
        in_memory_cache_after = getattr(source, '_cached_news_items', [])
        in_memory_cache_time_after = getattr(source, '_last_cache_update', 0)
        
        logger.info(f"In-memory cache after: {len(in_memory_cache_after)} items, last update: {in_memory_cache_time_after}")
        
        # 验证内存缓存是否已更新
        if len(in_memory_cache_after) == 0:
            logger.warning(f"In-memory cache is empty after fetch")
        
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
            return False
        
        # 详细打印几条缓存的新闻
        for idx, item in enumerate(cached_news[:3]):  # 只检查前3个
            logger.info(f"Cache item {idx+1}:")
            logger.info(f"  Title: {getattr(item, 'title', 'N/A')[:50]}...")
            logger.info(f"  URL: {getattr(item, 'url', 'N/A')}")
            logger.info(f"  Published at: {getattr(item, 'published_at', 'N/A')}")
        
        # 验证缓存 TTL
        if self.cache_manager.redis:
            try:
                ttl = await self.cache_manager.redis.ttl(cache_key)
                logger.info(f"Redis cache TTL: {ttl} seconds")
                if ttl <= 0:
                    logger.warning(f"Cache TTL is not set properly: {ttl}")
            except Exception as e:
                logger.error(f"Failed to get TTL: {str(e)}")
        
        # 验证内存缓存和Redis缓存数据是否一致
        if len(in_memory_cache_after) != len(cached_news):
            logger.warning(f"Cache size mismatch: in-memory={len(in_memory_cache_after)}, Redis={len(cached_news)}")
        
        logger.info(f"Kr36NewsSource Redis cache integration test completed successfully")
        return True
    
    async def run_test(self) -> bool:
        """
        运行测试
        
        Returns:
            测试结果
        """
        await self.initialize()
        
        try:
            # 运行Kr36测试
            result = await self.test_kr36_cache()
            logger.info(f"Test result: {'SUCCESS' if result else 'FAILED'}")
            return result
        finally:
            await self.cleanup()


async def main():
    """主函数"""
    # 创建测试器
    redis_url = os.environ.get('REDIS_URL')
    if not redis_url:
        logger.error("REDIS_URL environment variable not set")
        return
    
    tester = Kr36RedisCacheTester(redis_url)
    
    # 运行测试
    result = await tester.run_test()
    
    # 确定退出代码
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    asyncio.run(main()) 