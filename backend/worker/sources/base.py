import json
import os
import datetime
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

import redis

from app.core.config import settings


class NewsItemModel:
    """
    News item model for source adapters
    """
    
    def __init__(
        self,
        id: str,
        title: str,
        url: str,
        mobile_url: Optional[str] = None,
        content: Optional[str] = None,
        summary: Optional[str] = None,
        image_url: Optional[str] = None,
        published_at: Optional[datetime.datetime] = None,
        extra: Optional[Dict[str, Any]] = None
    ):
        self.id = id
        self.title = title
        self.url = url
        self.mobile_url = mobile_url
        self.content = content
        self.summary = summary
        self.image_url = image_url
        self.published_at = published_at
        self.extra = extra or {}


class NewsSource(ABC):
    """
    Base class for news sources
    """
    
    def __init__(
        self, 
        source_id: str, 
        name: str, 
        update_interval: int = 600,
        cache_ttl: int = 300,
        category: Optional[str] = None,
        country: Optional[str] = None,
        language: Optional[str] = None
    ):
        self.source_id = source_id
        self.name = name
        self.update_interval = update_interval
        self.cache_ttl = cache_ttl
        self.category = category
        self.country = country
        self.language = language
        self.redis = redis.Redis.from_url(settings.REDIS_URL)
    
    @abstractmethod
    async def fetch(self) -> List[NewsItemModel]:
        """
        Fetch news data from source
        """
        pass
    
    async def process(self) -> List[NewsItemModel]:
        """
        Process news data flow
        """
        # Check cache
        cached_news = self.get_cached_news()
        if cached_news:
            return [NewsItemModel(**item) for item in cached_news]
        
        # Fetch new data
        news_items = await self.fetch()
        
        # Update cache
        self.cache_news(news_items)
        self.update_last_fetch_time()
        
        return news_items
    
    def get_cached_news(self) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached news
        """
        cache_key = f"source:{self.source_id}:news"
        cached = self.redis.get(cache_key)
        if cached:
            return json.loads(cached)
        return None
    
    def cache_news(self, news_items: List[NewsItemModel]) -> None:
        """
        Cache news items
        """
        if not news_items:
            return
        
        # Convert to serializable format
        serializable_items = []
        for item in news_items:
            serializable_item = {
                "id": item.id,
                "title": item.title,
                "url": item.url,
                "mobile_url": item.mobile_url,
                "content": item.content,
                "summary": item.summary,
                "image_url": item.image_url,
                "extra": item.extra
            }
            
            # Handle datetime
            if item.published_at:
                serializable_item["published_at"] = item.published_at.isoformat()
            
            serializable_items.append(serializable_item)
        
        # Save to cache
        cache_key = f"source:{self.source_id}:news"
        self.redis.setex(
            cache_key,
            self.cache_ttl,
            json.dumps(serializable_items)
        )
    
    def update_last_fetch_time(self) -> None:
        """
        Update last fetch time
        """
        cache_key = f"source:{self.source_id}:last_fetch"
        self.redis.setex(
            cache_key,
            self.update_interval,
            datetime.datetime.utcnow().isoformat()
        )
    
    def get_last_fetch_time(self) -> Optional[datetime.datetime]:
        """
        Get last fetch time
        """
        cache_key = f"source:{self.source_id}:last_fetch"
        last_fetch = self.redis.get(cache_key)
        if last_fetch:
            return datetime.datetime.fromisoformat(last_fetch.decode())
        return None 