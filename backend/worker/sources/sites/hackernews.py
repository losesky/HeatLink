import logging
import asyncio
from typing import List, Dict, Any, Optional

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
            "max_items": 30,  # 最多获取30条新闻
            "max_concurrent": 10  # 最大并发请求数
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
        async with semaphore:
            try:
                # 获取新闻详情
                story_url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
                
                # 使用带重试的请求
                story_data = await self.fetch_with_retry(
                    url=story_url,
                    method="GET",
                    headers=self.headers,
                    response_type="json"
                )
                
                if not story_data or story_data.get("type") != "story":
                    return None
                
                # 生成唯一ID
                item_id = self.generate_id(str(story_id))
                
                # 获取标题
                title = story_data.get("title", "")
                if not title:
                    return None
                
                # 获取URL
                url = story_data.get("url", f"https://news.ycombinator.com/item?id={story_id}")
                
                # 获取发布时间
                time = story_data.get("time", 0)
                published_at = self.parse_date(str(time)) if time else None
                
                # 创建新闻项
                return self.create_news_item(
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
            except Exception as e:
                logger.error(f"Error fetching Hacker News story {story_id}: {str(e)}")
                return None
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从Hacker News API获取新闻，并行请求多个新闻详情
        """
        logger.info(f"Fetching news from Hacker News API: {self.api_url}")
        
        try:
            # 获取新闻ID列表
            story_ids = await self.fetch_with_retry(
                url=self.api_url,
                method="GET",
                headers=self.headers,
                response_type="json"
            )
            
            # 检查响应是否有效
            if not story_ids or not isinstance(story_ids, list):
                logger.error(f"Invalid Hacker News response: {story_ids}")
                return []
            
            # 获取前N条新闻的ID
            max_items = self.config.get("max_items", 30)
            story_ids = story_ids[:max_items]
            
            # 创建信号量限制并发请求数
            max_concurrent = self.config.get("max_concurrent", 10)
            semaphore = asyncio.Semaphore(max_concurrent)
            
            # 创建获取新闻详情的任务
            tasks = []
            for story_id in story_ids:
                tasks.append(self.fetch_story(story_id, semaphore))
            
            # 并行执行所有任务
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            news_items = []
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Error fetching Hacker News story: {str(result)}")
                    continue
                if result:  # 过滤掉None结果
                    news_items.append(result)
            
            logger.info(f"Fetched {len(news_items)} news items from Hacker News API")
            return news_items
        
        except Exception as e:
            logger.error(f"Error fetching news from Hacker News API: {str(e)}")
            raise 