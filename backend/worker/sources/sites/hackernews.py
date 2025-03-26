import logging
import asyncio
from typing import List, Dict, Any, Optional
import time

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource
from worker.utils.http_client import http_client

logger = logging.getLogger(__name__)


class HackerNewsSource(APINewsSource):
    """
    Hacker News新闻源适配器
    """
    
    def __init__(
        self,
        source_id: str = "hackernews",
        name: str = "Hacker News",
        api_url: str = "https://hacker-news.firebaseio.com/v0/topstories.json",
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "technology",
        country: str = "US",
        language: str = "en",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "application/json"
            },
            "max_items": 20,  # 最多获取20条新闻（减少数量以提高速度）
            "max_concurrent": 20,  # 增加最大并发请求数
            "item_timeout": 10,  # 单个项目超时时间（秒）
            "overall_timeout": 45  # 整体操作超时时间（秒）
        })
        
        super().__init__(
            source_id=source_id,
            name=name,
            api_url=api_url,
            update_interval=update_interval,
            cache_ttl=cache_ttl,
            category=category,
            country=country,
            language=language,
            config=config
        )
        
        # 缓存已获取的新闻条目
        self._news_cache = {}
        self._last_cache_update = 0
        self._cache_ttl = 3600  # 缓存有效期（秒）
        self._cache_lock = asyncio.Lock()
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析API响应
        
        由于HackerNews的fetch方法已经实现了获取和解析数据的逻辑，
        这个方法主要是为了满足抽象基类的要求。
        实际的解析逻辑在fetch方法中。
        """
        logger.warning("HackerNewsSource.parse_response被直接调用，这不是预期的使用方式。请使用fetch方法获取新闻。")
        return []
    
    async def fetch_story(self, story_id: int, semaphore: asyncio.Semaphore) -> Optional[NewsItemModel]:
        """获取单个新闻详情"""
        # 检查缓存
        cache_key = f"story_{story_id}"
        if cache_key in self._news_cache:
            cached_item = self._news_cache[cache_key]
            if cached_item is not None:
                logger.debug(f"从缓存获取 Hacker News 故事 {story_id}")
                return cached_item
        
        async with semaphore:
            try:
                # 使用较短的超时时间
                item_timeout = self.config.get("item_timeout", 10)
                
                # 获取新闻详情
                story_url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
                
                # 使用带重试但超时时间短的请求
                story_data = await self.fetch_with_retry(
                    url=story_url,
                    method="GET",
                    headers=self.headers,
                    response_type="json",
                    timeout=item_timeout,
                    max_retries=2,  # 减少重试次数以加快失败情况下的处理
                    retry_delay=0.5  # 减少重试延迟
                )
                
                if not story_data or story_data.get("type") != "story":
                    # 缓存None结果以避免重复请求无效故事
                    async with self._cache_lock:
                        self._news_cache[cache_key] = None
                    return None
                
                # 生成唯一ID
                item_id = self.generate_id(str(story_id))
                
                # 获取标题
                title = story_data.get("title", "")
                if not title:
                    async with self._cache_lock:
                        self._news_cache[cache_key] = None
                    return None
                
                # 获取URL
                url = story_data.get("url", f"https://news.ycombinator.com/item?id={story_id}")
                
                # 获取发布时间
                time_value = story_data.get("time", 0)
                published_at = self.parse_date(str(time_value)) if time_value else None
                
                # 创建新闻项
                news_item = self.create_news_item(
                    id=item_id,
                    title=title,
                    url=url,
                    content=story_data.get("text", ""),
                    summary=None,  # Hacker News没有提供摘要
                    image_url=None,  # Hacker News没有提供图片
                    published_at=published_at,
                    extra={
                        "is_top": False,
                        "mobile_url": url,  # Hacker News的移动版URL与PC版相同
                        "score": story_data.get("score", 0),
                        "by": story_data.get("by", ""),
                        "descendants": story_data.get("descendants", 0)
                    }
                )
                
                # 将结果添加到缓存
                async with self._cache_lock:
                    self._news_cache[cache_key] = news_item
                    self._last_cache_update = time.time()
                
                return news_item
            except Exception as e:
                logger.error(f"Error fetching Hacker News story {story_id}: {str(e)}")
                return None
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从Hacker News API获取新闻，并行请求多个新闻详情
        增加了超时控制和缓存机制，大幅提高响应速度
        """
        # 检查是否可以使用缓存
        current_time = time.time()
        if (current_time - self._last_cache_update < self._cache_ttl and 
            len(self._news_cache) > 0):
            
            # 从缓存获取有效的新闻条目
            cached_news = [item for item in self._news_cache.values() if item is not None]
            if len(cached_news) >= 5:  # 至少有5条有效新闻才使用缓存
                logger.info(f"从缓存获取到 {len(cached_news)} 条 Hacker News 新闻")
                return cached_news
        
        logger.info(f"Fetching news from Hacker News API: {self.api_url}")
        start_time = time.time()
        
        # 设置整体操作超时时间
        overall_timeout = self.config.get("overall_timeout", 45)
        
        try:
            # 创建超时任务
            fetch_task = asyncio.create_task(self._fetch_impl())
            
            # 使用超时控制
            try:
                news_items = await asyncio.wait_for(fetch_task, timeout=overall_timeout)
                
                # 记录执行时间
                elapsed = time.time() - start_time
                logger.info(f"完成获取 Hacker News，执行时间: {elapsed:.2f}秒")
                
                return news_items
            except asyncio.TimeoutError:
                logger.warning(f"获取 Hacker News 超时 ({overall_timeout}秒)，返回已获取的缓存项目")
                # 如果超时，尝试返回已缓存的项目
                cached_news = [item for item in self._news_cache.values() if item is not None]
                if cached_news:
                    logger.info(f"从缓存返回 {len(cached_news)} 条新闻")
                    return cached_news
                # 如果缓存为空，返回空列表
                logger.error("获取 Hacker News 超时且缓存为空")
                return []
        
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Error fetching news from Hacker News API: {str(e)} (用时 {elapsed:.2f}秒)")
            # 尝试返回缓存结果
            cached_news = [item for item in self._news_cache.values() if item is not None]
            if cached_news:
                logger.info(f"从缓存返回 {len(cached_news)} 条新闻")
                return cached_news
            raise
    
    async def _fetch_impl(self) -> List[NewsItemModel]:
        """实际执行获取操作的内部方法"""
        try:
            # 使用较短的超时时间获取顶级故事ID列表
            story_ids = await self.fetch_with_retry(
                url=self.api_url,
                method="GET",
                headers=self.headers,
                response_type="json",
                timeout=10,  # 短超时
                max_retries=2,  # 少重试
                retry_delay=0.5  # 短延迟
            )
            
            # 检查响应是否有效
            if not story_ids or not isinstance(story_ids, list):
                logger.error(f"Invalid Hacker News response: {story_ids}")
                return []
            
            # 获取前N条新闻的ID
            max_items = self.config.get("max_items", 20)
            story_ids = story_ids[:max_items]
            
            # 创建信号量限制并发请求数
            max_concurrent = self.config.get("max_concurrent", 20)
            semaphore = asyncio.Semaphore(max_concurrent)
            
            # 创建获取新闻详情的任务
            tasks = []
            for story_id in story_ids:
                tasks.append(self.fetch_story(story_id, semaphore))
            
            # 使用as_completed方式收集结果，便于尽早处理完成的任务
            news_items = []
            for future in asyncio.as_completed(tasks, timeout=30):
                try:
                    result = await future
                    if result:  # 过滤掉None结果
                        news_items.append(result)
                except Exception as e:
                    logger.error(f"处理 Hacker News 故事时出错: {str(e)}")
            
            logger.info(f"Fetched {len(news_items)} news items from Hacker News API")
            
            # 更新缓存时间
            self._last_cache_update = time.time()
            
            return news_items
        except Exception as e:
            logger.error(f"实现获取 Hacker News 时出错: {str(e)}")
            return []
    
    # 清理过期缓存
    async def clean_cache(self):
        """清理过期的缓存项目"""
        current_time = time.time()
        if current_time - self._last_cache_update > self._cache_ttl:
            async with self._cache_lock:
                self._news_cache.clear()
                logger.info("已清理 Hacker News 缓存")
    
    # 重写关闭方法，确保清理资源
    async def close(self):
        """关闭资源"""
        # 清理缓存
        await self.clean_cache()
        # 调用父类方法
        await super().close() 