import logging
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource

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
            "max_items": 30  # 最多获取30条新闻
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
    
    async def parse_response(self, response: Any) -> List[NewsItemModel]:
        """
        解析Hacker News API响应
        """
        try:
            news_items = []
            
            # 检查响应是否有效
            if not response or not isinstance(response, list):
                logger.error(f"Invalid Hacker News response: {response}")
                return []
            
            # 获取前N条新闻的ID
            max_items = self.config.get("max_items", 30)
            story_ids = response[:max_items]
            
            # 获取每条新闻的详细信息
            for story_id in story_ids:
                try:
                    # 获取新闻详情
                    story_url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
                    story_data = await http_client.fetch(
                        url=story_url,
                        method="GET",
                        headers=self.headers,
                        response_type="json"
                    )
                    
                    if not story_data or story_data.get("type") != "story":
                        continue
                    
                    # 生成唯一ID
                    item_id = self.generate_id(str(story_id))
                    
                    # 获取标题
                    title = story_data.get("title", "")
                    if not title:
                        continue
                    
                    # 获取URL
                    url = story_data.get("url", f"https://news.ycombinator.com/item?id={story_id}")
                    
                    # 获取发布时间
                    time = story_data.get("time", 0)
                    published_at = self.parse_date(str(time)) if time else None
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=item_id,
                        title=title,
                        url=url,
                        mobile_url=url,  # Hacker News的移动版URL与PC版相同
                        content=story_data.get("text", ""),
                        summary=None,  # Hacker News没有提供摘要
                        image_url=None,  # Hacker News没有提供图片
                        published_at=published_at,
                        is_top=False,
                        extra={
                            "source_id": self.source_id,
                            "source_name": self.name,
                            "score": story_data.get("score", 0),
                            "by": story_data.get("by", ""),
                            "descendants": story_data.get("descendants", 0)
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing Hacker News item {story_id}: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing Hacker News response: {str(e)}")
            return []
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从Hacker News API获取新闻
        重写fetch方法，因为需要先获取新闻ID列表，再获取每条新闻的详细信息
        """
        from worker.utils.http_client import http_client
        
        logger.info(f"Fetching news from Hacker News API: {self.api_url}")
        
        try:
            # 获取新闻ID列表
            story_ids = await http_client.fetch(
                url=self.api_url,
                method="GET",
                headers=self.headers,
                response_type="json"
            )
            
            # 解析响应
            news_items = await self.parse_response(story_ids)
            
            logger.info(f"Fetched {len(news_items)} news items from Hacker News API")
            return news_items
        
        except Exception as e:
            logger.error(f"Error fetching news from Hacker News API: {str(e)}")
            raise 