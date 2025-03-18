import logging
import hashlib
import datetime
import json
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource
from worker.utils.http_client import http_client

logger = logging.getLogger(__name__)

class ZhihuDailyNewsSource(APINewsSource):
    """
    知乎日报适配器
    直接从知乎官方API获取数据，不依赖第三方RSS服务
    """
    
    # 官方API URL
    API_URL = "https://daily.zhihu.com/api/4/news/latest"
    
    # 备用API URL列表，如果主URL无法访问，可以尝试备用URL
    BACKUP_URLS = [
        "https://news-at.zhihu.com/api/4/news/latest"
    ]
    
    def __init__(
        self,
        source_id: str = "zhihu_daily",
        name: str = "知乎日报",
        api_url: str = API_URL,
        update_interval: int = 3600,  # 1小时更新一次
        cache_ttl: int = 1800,  # 30分钟
        category: str = "knowledge",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "application/json",
                "Referer": "https://daily.zhihu.com/"
            },
            # 添加备用API URL
            "backup_urls": self.BACKUP_URLS,
            "max_retries": 3,
            "retry_delay": 2
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
        
        logger.info(f"Initialized {self.name} adapter with API URL: {self.api_url}")
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        获取知乎日报最新内容
        """
        logger.info("Fetching Zhihu Daily")
        
        urls_to_try = [self.api_url] + self.config.get("backup_urls", [])
        max_retries = self.config.get("max_retries", 3)
        
        last_error = None
        for url in urls_to_try:
            logger.info(f"Trying API URL: {url}")
            
            for attempt in range(max_retries):
                try:
                    response = await http_client.fetch(
                        url=url,
                        method="GET",
                        headers=self.headers,
                        response_type="json",
                        timeout=10
                    )
                    
                    if response:
                        logger.info(f"Successfully fetched from API: {url}")
                        return await self.parse_response(response)
                    
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"Error fetching from API (attempt {attempt+1}/{max_retries}): {last_error}")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in {self.config.get('retry_delay', 2)} seconds...")
                        import asyncio
                        await asyncio.sleep(self.config.get("retry_delay", 2))
        
        logger.error(f"All API URLs failed. Last error: {last_error}")
        return []
    
    async def parse_response(self, response: Dict[str, Any]) -> List[NewsItemModel]:
        """
        解析知乎日报API响应
        """
        if not response or not isinstance(response, dict):
            logger.error("Invalid API response format")
            return []
        
        stories = response.get("stories", [])
        if not stories:
            logger.warning("No stories found in API response")
            return []
        
        logger.info(f"Found {len(stories)} stories in API response")
        
        news_items = []
        for index, story in enumerate(stories):
            try:
                # 提取必要字段
                story_id = story.get("id")
                if not story_id:
                    continue
                
                title = story.get("title")
                if not title:
                    continue
                
                # 构建URL
                url = story.get("url") or f"https://daily.zhihu.com/story/{story_id}"
                
                # 提取图片
                image_url = None
                if "images" in story and story["images"] and len(story["images"]) > 0:
                    image_url = story["images"][0]
                
                # 生成ID
                item_id = hashlib.md5(f"{self.source_id}:{story_id}".encode()).hexdigest()
                
                # 创建NewsItem
                news_item = self.create_news_item(
                    id=item_id,
                    title=title,
                    url=url,
                    content=story.get("hint", ""),  # 使用提示作为内容
                    summary=story.get("hint", ""),  # 使用提示作为摘要
                    image_url=image_url,
                    published_at=datetime.datetime.now(datetime.timezone.utc),  # 使用当前时间，因为API没有提供发布时间
                    extra={
                        "source_id": self.source_id,
                        "source_name": self.name,
                        "story_id": story_id,
                        "rank": index + 1,
                        "hint": story.get("hint", ""),
                        "ga_prefix": story.get("ga_prefix", ""),
                        "image_hue": story.get("image_hue", "")
                    }
                )
                
                news_items.append(news_item)
                
            except Exception as e:
                logger.error(f"Error processing story: {str(e)}")
                continue
        
        logger.info(f"Successfully parsed {len(news_items)} news items")
        return news_items 