import logging
import asyncio
import time
import datetime
from typing import Dict, List, Any, Optional, Set

from worker.sources.base import NewsSource
from worker.sources.factory import NewsSourceFactory
from worker.cache import CacheManager

logger = logging.getLogger(__name__)


class AdaptiveScheduler:
    """
    自适应调度器
    根据数据源的更新频率和重要性动态调整抓取任务的执行频率
    """
    
    def __init__(
        self,
        cache_manager: CacheManager,
        min_interval: int = 120,  # 最小抓取间隔，单位秒，默认2分钟
        max_interval: int = 3600,  # 最大抓取间隔，单位秒，默认1小时
        enable_adaptive: bool = True,  # 是否启用自适应调度
        enable_cache: bool = True,  # 是否启用缓存
    ):
        self.cache_manager = cache_manager
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.enable_adaptive = enable_adaptive
        self.enable_cache = enable_cache
        
        # 存储所有数据源
        self.sources: Dict[str, NewsSource] = {}
        
        # 存储数据源的最后抓取时间
        self.last_fetch_time: Dict[str, float] = {}
        
        # 存储数据源的动态调整后的抓取间隔
        self.dynamic_intervals: Dict[str, int] = {}
        
        # 存储数据源的抓取成功率
        self.success_rates: Dict[str, float] = {}
        
        # 存储数据源的更新频率评分
        self.update_frequency_scores: Dict[str, float] = {}
        
        # 存储正在执行的任务
        self.running_tasks: Set[str] = set()
        
        # 初始化标志
        self.initialized = False
    
    async def initialize(self):
        """
        初始化调度器
        """
        if self.initialized:
            return
        
        # 创建默认数据源
        sources = NewsSourceFactory.create_default_sources()
        
        # 注册数据源
        for source in sources:
            self.register_source(source)
        
        # 初始化完成
        self.initialized = True
        logger.info(f"Scheduler initialized with {len(self.sources)} sources")
    
    def register_source(self, source: NewsSource):
        """
        注册数据源
        """
        source_id = source.source_id
        
        # 存储数据源
        self.sources[source_id] = source
        
        # 初始化最后抓取时间
        self.last_fetch_time[source_id] = 0
        
        # 初始化动态调整后的抓取间隔，使用数据源的默认更新间隔
        self.dynamic_intervals[source_id] = source.update_interval
        
        # 初始化抓取成功率
        self.success_rates[source_id] = 1.0
        
        # 初始化更新频率评分
        self.update_frequency_scores[source_id] = 0.5  # 初始评分为中等
        
        logger.info(f"Registered source: {source_id}, update interval: {source.update_interval}s")
    
    def unregister_source(self, source_id: str):
        """
        注销数据源
        """
        if source_id in self.sources:
            del self.sources[source_id]
            del self.last_fetch_time[source_id]
            del self.dynamic_intervals[source_id]
            del self.success_rates[source_id]
            del self.update_frequency_scores[source_id]
            logger.info(f"Unregistered source: {source_id}")
    
    def get_source(self, source_id: str) -> Optional[NewsSource]:
        """
        获取数据源
        """
        return self.sources.get(source_id)
    
    def get_all_sources(self) -> List[NewsSource]:
        """
        获取所有数据源
        """
        return list(self.sources.values())
    
    def should_fetch(self, source_id: str) -> bool:
        """
        判断是否应该抓取数据源
        """
        # 如果数据源不存在，则不抓取
        if source_id not in self.sources:
            return False
        
        # 如果数据源正在抓取，则不重复抓取
        if source_id in self.running_tasks:
            return False
        
        # 获取当前时间
        current_time = time.time()
        
        # 获取最后抓取时间
        last_time = self.last_fetch_time.get(source_id, 0)
        
        # 获取动态调整后的抓取间隔
        interval = self.dynamic_intervals.get(source_id, self.sources[source_id].update_interval)
        
        # 判断是否应该抓取
        return current_time - last_time >= interval
    
    async def fetch_source(self, source_id: str, force: bool = False) -> bool:
        """
        抓取数据源
        """
        # 如果数据源不存在，则返回失败
        if source_id not in self.sources:
            logger.error(f"Source not found: {source_id}")
            return False
        
        # 如果数据源正在抓取，则返回失败
        if source_id in self.running_tasks:
            logger.warning(f"Source is already being fetched: {source_id}")
            return False
        
        # 如果不是强制抓取，且不应该抓取，则返回失败
        if not force and not self.should_fetch(source_id):
            return False
        
        # 标记数据源正在抓取
        self.running_tasks.add(source_id)
        
        try:
            # 获取数据源
            source = self.sources[source_id]
            
            # 记录开始时间
            start_time = time.time()
            
            # 尝试从缓存获取数据
            cache_key = f"source:{source_id}"
            cached_data = None
            
            if self.enable_cache and not force:
                cached_data = await self.cache_manager.get(cache_key)
            
            # 如果缓存中有数据，则直接返回
            if cached_data:
                logger.info(f"Using cached data for source: {source_id}")
                # 更新最后抓取时间
                self.last_fetch_time[source_id] = start_time
                return True
            
            # 抓取数据
            logger.info(f"Fetching data from source: {source_id}")
            news_items = await source.fetch()
            
            # 记录结束时间
            end_time = time.time()
            
            # 计算抓取耗时
            fetch_time = end_time - start_time
            
            # 更新最后抓取时间
            self.last_fetch_time[source_id] = end_time
            
            # 如果抓取成功
            if news_items:
                # 更新抓取成功率
                self.success_rates[source_id] = 0.9 * self.success_rates[source_id] + 0.1
                
                # 如果启用缓存，则将数据存入缓存
                if self.enable_cache:
                    # 使用数据源的缓存TTL
                    ttl = source.cache_ttl
                    await self.cache_manager.set(cache_key, news_items, ttl)
                
                # 如果启用自适应调度，则调整抓取间隔
                if self.enable_adaptive:
                    self._adjust_interval(source_id, news_items, fetch_time)
                
                logger.info(f"Successfully fetched {len(news_items)} items from source: {source_id}, time: {fetch_time:.2f}s")
                return True
            else:
                # 更新抓取成功率
                self.success_rates[source_id] = 0.9 * self.success_rates[source_id]
                
                # 如果启用自适应调度，则增加抓取间隔
                if self.enable_adaptive:
                    self._increase_interval(source_id)
                
                logger.warning(f"No data fetched from source: {source_id}, time: {fetch_time:.2f}s")
                return False
        except Exception as e:
            # 更新抓取成功率
            self.success_rates[source_id] = 0.9 * self.success_rates[source_id]
            
            # 如果启用自适应调度，则增加抓取间隔
            if self.enable_adaptive:
                self._increase_interval(source_id)
            
            logger.error(f"Error fetching data from source: {source_id}, error: {str(e)}")
            return False
        finally:
            # 标记数据源抓取完成
            self.running_tasks.remove(source_id)
    
    def _adjust_interval(self, source_id: str, news_items: List[Any], fetch_time: float):
        """
        调整抓取间隔
        """
        # 获取数据源
        source = self.sources[source_id]
        
        # 获取当前动态间隔
        current_interval = self.dynamic_intervals[source_id]
        
        # 获取数据源的默认更新间隔
        default_interval = source.update_interval
        
        # 获取数据项的数量
        item_count = len(news_items)
        
        # 获取最新数据项的发布时间
        latest_time = None
        for item in news_items:
            if hasattr(item, 'published_at') and item.published_at:
                if latest_time is None or item.published_at > latest_time:
                    latest_time = item.published_at
        
        # 如果有最新数据项的发布时间
        if latest_time:
            # 计算最新数据项的发布时间与当前时间的差值
            now = datetime.datetime.now()
            time_diff = (now - latest_time).total_seconds()
            
            # 根据时间差值计算更新频率评分
            # 时间差值越小，评分越高
            if time_diff < 300:  # 5分钟内
                frequency_score = 0.9
            elif time_diff < 900:  # 15分钟内
                frequency_score = 0.7
            elif time_diff < 1800:  # 30分钟内
                frequency_score = 0.5
            elif time_diff < 3600:  # 1小时内
                frequency_score = 0.3
            else:
                frequency_score = 0.1
            
            # 更新频率评分
            self.update_frequency_scores[source_id] = 0.7 * self.update_frequency_scores[source_id] + 0.3 * frequency_score
        
        # 根据数据项数量、抓取耗时和更新频率评分计算新的抓取间隔
        # 数据项数量越多，抓取耗时越短，更新频率评分越高，抓取间隔越短
        score = self.update_frequency_scores[source_id] * 0.6 + self.success_rates[source_id] * 0.4
        
        if score > 0.8:
            # 高分，减少间隔
            new_interval = max(self.min_interval, int(default_interval * 0.5))
        elif score > 0.6:
            # 中高分，略微减少间隔
            new_interval = max(self.min_interval, int(default_interval * 0.8))
        elif score > 0.4:
            # 中等分，使用默认间隔
            new_interval = default_interval
        elif score > 0.2:
            # 中低分，略微增加间隔
            new_interval = min(self.max_interval, int(default_interval * 1.2))
        else:
            # 低分，增加间隔
            new_interval = min(self.max_interval, int(default_interval * 1.5))
        
        # 更新动态间隔
        if new_interval != current_interval:
            self.dynamic_intervals[source_id] = new_interval
            logger.info(f"Adjusted interval for source: {source_id}, from {current_interval}s to {new_interval}s, score: {score:.2f}")
    
    def _increase_interval(self, source_id: str):
        """
        增加抓取间隔
        """
        # 获取当前动态间隔
        current_interval = self.dynamic_intervals[source_id]
        
        # 增加间隔，最多增加到最大间隔
        new_interval = min(self.max_interval, int(current_interval * 1.5))
        
        # 更新动态间隔
        if new_interval != current_interval:
            self.dynamic_intervals[source_id] = new_interval
            logger.info(f"Increased interval for source: {source_id}, from {current_interval}s to {new_interval}s")
    
    async def run_once(self, force: bool = False):
        """
        运行一次调度
        """
        # 确保初始化完成
        if not self.initialized:
            await self.initialize()
        
        # 获取所有数据源ID
        source_ids = list(self.sources.keys())
        
        # 遍历所有数据源
        for source_id in source_ids:
            # 判断是否应该抓取
            if force or self.should_fetch(source_id):
                # 抓取数据源
                await self.fetch_source(source_id, force)
    
    async def run_forever(self, check_interval: int = 10):
        """
        持续运行调度
        """
        # 确保初始化完成
        if not self.initialized:
            await self.initialize()
        
        logger.info("Scheduler started")
        
        try:
            while True:
                # 运行一次调度
                await self.run_once()
                
                # 等待一段时间
                await asyncio.sleep(check_interval)
        except asyncio.CancelledError:
            logger.info("Scheduler stopped")
        except Exception as e:
            logger.error(f"Scheduler error: {str(e)}")
            raise
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取调度器状态
        """
        status = {
            "sources_count": len(self.sources),
            "running_tasks": len(self.running_tasks),
            "sources": []
        }
        
        # 获取所有数据源状态
        for source_id, source in self.sources.items():
            last_fetch = self.last_fetch_time.get(source_id, 0)
            last_fetch_time = datetime.datetime.fromtimestamp(last_fetch).isoformat() if last_fetch > 0 else None
            
            next_fetch = last_fetch + self.dynamic_intervals.get(source_id, source.update_interval)
            next_fetch_time = datetime.datetime.fromtimestamp(next_fetch).isoformat() if next_fetch > 0 else None
            
            source_status = {
                "id": source_id,
                "name": source.name,
                "category": source.category,
                "default_interval": source.update_interval,
                "dynamic_interval": self.dynamic_intervals.get(source_id, source.update_interval),
                "last_fetch_time": last_fetch_time,
                "next_fetch_time": next_fetch_time,
                "success_rate": self.success_rates.get(source_id, 0),
                "update_frequency_score": self.update_frequency_scores.get(source_id, 0),
                "is_running": source_id in self.running_tasks
            }
            
            status["sources"].append(source_status)
        
        return status 