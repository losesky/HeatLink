import logging
import asyncio
import time
import datetime
from typing import Dict, List, Any, Optional, Set

# 引入接口而不是具体实现
from worker.sources.interface import NewsSourceInterface  
from worker.sources.provider import NewsSourceProvider
from worker.cache import CacheManager

logger = logging.getLogger(__name__)


class AdaptiveScheduler:
    """
    自适应调度器
    根据数据源的更新频率和重要性动态调整抓取任务的执行频率
    """
    
    def __init__(
        self,
        source_provider: NewsSourceProvider,  # 使用提供者接口
        cache_manager: CacheManager,
        min_interval: int = 120,  # 最小抓取间隔，单位秒，默认2分钟
        max_interval: int = 3600,  # 最大抓取间隔，单位秒，默认1小时
        enable_adaptive: bool = True,  # 是否启用自适应调度
        enable_cache: bool = True,  # 是否启用缓存
        api_base_url: str = None,  # API基础URL，如果设置，将通过API获取数据
    ):
        self.source_provider = source_provider  # 保存提供者引用
        self.cache_manager = cache_manager
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.enable_adaptive = enable_adaptive
        self.enable_cache = enable_cache
        self.api_base_url = api_base_url  # 保存API基础URL
        
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
        
        # 获取所有源，从提供者获取而不是自己创建
        sources = self.source_provider.get_all_sources()
        
        # 初始化每个源的状态
        for source in sources:
            self._initialize_source_state(source)
        
        # 初始化完成
        self.initialized = True
        logger.info(f"Scheduler initialized with {len(sources)} sources")
    
    def _initialize_source_state(self, source: NewsSourceInterface):
        """
        初始化新闻源状态
        """
        source_id = source.source_id
        
        # 初始化最后抓取时间
        self.last_fetch_time[source_id] = 0
        
        # 初始化动态调整后的抓取间隔，使用数据源的默认更新间隔
        self.dynamic_intervals[source_id] = source.update_interval
        
        # 初始化抓取成功率
        self.success_rates[source_id] = 1.0
        
        # 初始化更新频率评分
        self.update_frequency_scores[source_id] = 0.5  # 初始评分为中等

    def should_fetch(self, source_id: str) -> bool:
        """
        判断是否应该抓取数据源
        """
        # 获取源
        source = self.source_provider.get_source(source_id)
        
        # 如果数据源不存在，则不抓取
        if not source:
            return False
        
        # 如果数据源正在抓取，则不重复抓取
        if source_id in self.running_tasks:
            return False
        
        # 获取当前时间
        current_time = time.time()
        
        # 获取最后抓取时间
        last_time = self.last_fetch_time.get(source_id, 0)
        
        # 获取动态调整后的抓取间隔
        interval = self.dynamic_intervals.get(source_id, source.update_interval)
        
        # 判断是否应该抓取
        return current_time - last_time >= interval
    
    async def fetch_source(self, source_id: str, force: bool = False) -> bool:
        """
        抓取单个数据源
        
        Args:
            source_id: 数据源ID
            force: 是否强制抓取，即使不满足抓取条件
            
        Returns:
            是否成功抓取
        """
        # 如果数据源不存在，则不抓取
        source = self.source_provider.get_source(source_id)
        if not source:
            logger.warning(f"Source {source_id} not found")
            return False
        
        # 如果数据源正在抓取，则不重复抓取
        if source_id in self.running_tasks:
            logger.warning(f"Source {source_id} is already being fetched")
            return False
            
        # 如果不是强制抓取，且不满足抓取条件，则不抓取
        if not force and not self.should_fetch(source_id):
            return False
        
        # 标记为正在抓取
        self.running_tasks.add(source_id)
        
        try:
            # 记录开始时间
            start_time = time.time()
            
            # 通过API抓取数据或直接从源抓取
            try:
                # 尝试通过API获取数据
                if hasattr(self, 'api_base_url') and self.api_base_url:
                    news_items = await self._fetch_source_via_api(source_id, force)
                    logger.info(f"Fetched source {source_id} via API")
                else:
                    # 如果没有设置API基础URL，则直接从源获取
                    news_items = await source.get_news(force_update=force)
                    logger.info(f"Fetched source {source_id} directly from source")
                success = True
                error = None
            except Exception as e:
                logger.exception(f"Error fetching source {source_id}: {str(e)}")
                news_items = []
                success = False
                error = e
            
            # 记录结束时间
            end_time = time.time()
            
            # 更新最后抓取时间
            self.last_fetch_time[source_id] = end_time
            
            # 更新源的指标
            source.update_metrics(len(news_items), success, error)
            
            # 调整抓取间隔
            if self.enable_adaptive:
                self._adjust_interval(source_id, news_items, end_time - start_time)
            
            if success:
                logger.info(f"Successfully fetched {len(news_items)} items from {source_id} in {end_time - start_time:.2f}s")
                
                # 将新闻条目保存到Redis缓存
                if self.cache_manager and news_items:
                    try:
                        cache_key = f"source:{source_id}"
                        # 使用源的cache_ttl作为Redis缓存的过期时间
                        ttl = getattr(source, 'cache_ttl', 900)  # 默认15分钟
                        await self.cache_manager.set(cache_key, news_items, ttl)
                        logger.info(f"Saved {len(news_items)} news items to Redis cache with key: {cache_key}, TTL: {ttl}s")
                    except Exception as cache_error:
                        logger.error(f"Failed to save news items to Redis cache: {str(cache_error)}")
            else:
                logger.error(f"Failed to fetch from {source_id} after {end_time - start_time:.2f}s")
                
            return success
        finally:
            # 移除正在抓取标记
            self.running_tasks.remove(source_id)
    
    async def _fetch_source_via_api(self, source_id: str, force: bool = False) -> List[Any]:
        """
        通过API抓取数据源
        
        Args:
            source_id: 数据源ID
            force: 是否强制抓取
            
        Returns:
            新闻列表
        """
        import aiohttp
        from worker.sources.base import NewsItemModel
        
        # 构建API URL
        url = f"{self.api_base_url}/api/sources/external/{source_id}/news"
        if force:
            url += "?force_update=true"
        
        # 发送请求
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API error: {response.status} - {error_text}")
                
                # 解析响应
                data = await response.json()
                
                # 将JSON数据转换为NewsItemModel对象
                news_items = []
                for item_data in data:
                    news_item = NewsItemModel.from_dict(item_data)
                    news_items.append(news_item)
                
                return news_items
    
    def get_all_sources(self) -> List[NewsSourceInterface]:
        """
        获取所有数据源
        
        Returns:
            所有数据源列表
        """
        return self.source_provider.get_all_sources()
    
    def get_source(self, source_id: str) -> Optional[NewsSourceInterface]:
        """
        获取数据源
        
        Args:
            source_id: 数据源ID
            
        Returns:
            数据源对象
        """
        return self.source_provider.get_source(source_id)
    
    def _adjust_interval(self, source_id: str, news_items: List[Any], fetch_time: float):
        """
        调整抓取间隔
        """
        # 获取数据源
        source = self.source_provider.get_source(source_id)
        
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