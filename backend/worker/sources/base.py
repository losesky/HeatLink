import json
import uuid
import time
import logging
import asyncio
import hashlib
import datetime
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union, Tuple

import aiohttp
from bs4 import BeautifulSoup

from worker.sources.config import settings

# 设置日志
logger = logging.getLogger(__name__)


class NewsItemModel:
    """
    新闻条目模型
    """
    def __init__(
        self,
        id: str = "",
        title: str = "",
        url: str = "",
        source_id: str = "",
        source_name: str = "",
        published_at: Optional[datetime.datetime] = None,
        updated_at: Optional[datetime.datetime] = None,
        summary: str = "",
        content: str = "",
        author: str = "",
        category: str = "",
        tags: List[str] = None,
        image_url: str = "",
        language: str = "",
        country: str = "",
        extra: Dict[str, Any] = None
    ):
        self.id = id
        self.title = title
        self.url = url
        self.source_id = source_id
        self.source_name = source_name
        self.published_at = published_at or datetime.datetime.now()
        self.updated_at = updated_at or datetime.datetime.now()
        self.summary = summary
        self.content = content
        self.author = author
        self.category = category
        self.tags = tags or []
        self.image_url = image_url
        self.language = language
        self.country = country
        self.extra = extra or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典
        """
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "summary": self.summary,
            "content": self.content,
            "author": self.author,
            "category": self.category,
            "tags": self.tags,
            "image_url": self.image_url,
            "language": self.language,
            "country": self.country,
            "extra": self.extra
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NewsItemModel':
        """
        从字典创建
        """
        # 处理日期字段
        published_at = data.get("published_at")
        if published_at and isinstance(published_at, str):
            try:
                published_at = datetime.datetime.fromisoformat(published_at)
            except ValueError:
                published_at = None
        
        updated_at = data.get("updated_at")
        if updated_at and isinstance(updated_at, str):
            try:
                updated_at = datetime.datetime.fromisoformat(updated_at)
            except ValueError:
                updated_at = None
        
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            url=data.get("url", ""),
            source_id=data.get("source_id", ""),
            source_name=data.get("source_name", ""),
            published_at=published_at,
            updated_at=updated_at,
            summary=data.get("summary", ""),
            content=data.get("content", ""),
            author=data.get("author", ""),
            category=data.get("category", ""),
            tags=data.get("tags", []),
            image_url=data.get("image_url", ""),
            language=data.get("language", ""),
            country=data.get("country", ""),
            extra=data.get("extra", {})
        )


class NewsSource(ABC):
    """
    新闻源基类
    """
    def __init__(
        self,
        source_id: str,
        name: str,
        category: str = "",
        country: str = "",
        language: str = "",
        update_interval: int = 1800,  # 默认30分钟更新一次
        cache_ttl: int = 900,  # 默认缓存15分钟
        config: Dict[str, Any] = None
    ):
        self.source_id = source_id
        self.name = name
        self.category = category
        self.country = country
        self.language = language
        self.update_interval = update_interval
        self.cache_ttl = cache_ttl
        self.config = config or {}
        self._http_client = None
        self._last_fetch_time = 0
        self._last_fetch_count = 0
        self._fetch_count = 0
        self._success_count = 0
        self._error_count = 0
        
        # 添加自适应更新频率相关属性
        self.last_update_time = 0  # 上次更新时间戳
        self.last_update_count = 0  # 上次更新获取的新闻数量
        self.update_history = []  # 更新历史记录
        self.min_update_interval = 120  # 最小更新间隔（秒）
        self.max_update_interval = 7200  # 最大更新间隔（秒）
        self.adaptive_interval = update_interval  # 当前自适应间隔
    
    @property
    def http_client(self) -> aiohttp.ClientSession:
        """
        获取HTTP客户端
        """
        if self._http_client is None or self._http_client.closed:
            self._http_client = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                },
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._http_client
    
    async def close(self):
        """
        关闭资源，子类可以重写此方法以释放额外资源
        """
        if hasattr(self, '_http_client') and self._http_client is not None:
            if hasattr(self._http_client, 'close') and callable(self._http_client.close):
                await self._http_client.close()
                self._http_client = None
    
    @abstractmethod
    async def fetch(self) -> List[NewsItemModel]:
        """
        抓取新闻
        """
        pass
    
    def generate_id(self, url: str, title: str = "", published_at: Optional[datetime.datetime] = None) -> str:
        """
        生成唯一ID
        """
        # 使用URL、标题和发布时间生成唯一ID
        content = url
        if title:
            content += title
        if published_at:
            content += published_at.isoformat()
        
        # 使用MD5生成ID
        return hashlib.md5(content.encode("utf-8")).hexdigest()
    
    async def extract_text_from_html(self, html: str, selector: str = None) -> str:
        """
        从HTML中提取文本
        """
        if not html:
            return ""
        
        soup = BeautifulSoup(html, "html.parser")
        
        # 移除脚本和样式
        for script in soup(["script", "style"]):
            script.extract()
        
        # 如果提供了选择器，则只提取选择器匹配的内容
        if selector:
            content = soup.select_one(selector)
            if content:
                return content.get_text(separator="\n").strip()
            else:
                return ""
        
        # 否则提取所有文本
        return soup.get_text(separator="\n").strip()
    
    async def generate_summary(self, content: str, max_length: int = 200) -> str:
        """
        生成摘要
        """
        if not content:
            return ""
        
        # 简单截取前N个字符作为摘要
        summary = content.strip().replace("\n", " ")
        if len(summary) > max_length:
            summary = summary[:max_length] + "..."
        
        return summary
    
    def should_update(self) -> bool:
        """
        判断是否应该更新
        基于自适应更新间隔
        """
        current_time = time.time()
        time_since_last_update = current_time - self.last_update_time
        
        # 如果从未更新过，或者已经超过自适应间隔，则应该更新
        return self.last_update_time == 0 or time_since_last_update >= self.adaptive_interval
    
    def update_adaptive_interval(self, news_count: int) -> None:
        """
        更新自适应间隔
        根据新闻数量动态调整更新频率
        
        策略：
        1. 如果新闻数量增加，减少更新间隔
        2. 如果新闻数量减少或不变，增加更新间隔
        3. 保持在最小和最大间隔之间
        """
        current_time = time.time()
        
        # 记录本次更新
        self.update_history.append({
            "time": current_time,
            "count": news_count
        })
        
        # 保留最近10次更新记录
        if len(self.update_history) > 10:
            self.update_history = self.update_history[-10:]
        
        # 如果有足够的历史记录，计算自适应间隔
        if len(self.update_history) >= 3:
            # 计算平均新闻增长率
            avg_growth_rate = 0
            for i in range(1, len(self.update_history)):
                prev = self.update_history[i-1]
                curr = self.update_history[i]
                time_diff = curr["time"] - prev["time"]
                count_diff = curr["count"] - prev["count"]
                
                # 避免除以零
                if time_diff > 0:
                    growth_rate = count_diff / time_diff
                    avg_growth_rate += growth_rate
            
            avg_growth_rate /= (len(self.update_history) - 1)
            
            # 根据增长率调整间隔
            if avg_growth_rate > 0.1:  # 快速增长
                self.adaptive_interval = max(self.min_update_interval, self.adaptive_interval * 0.8)
            elif avg_growth_rate < 0:  # 减少或不变
                self.adaptive_interval = min(self.max_update_interval, self.adaptive_interval * 1.2)
            
            logger.debug(f"Source {self.source_id} adaptive interval updated to {self.adaptive_interval}s")
        
        # 更新最后更新时间和数量
        self.last_update_time = current_time
        self.last_update_count = news_count
    
    async def get_news(self, force_update: bool = False) -> List[NewsItemModel]:
        """
        获取新闻，支持强制更新
        """
        if force_update or self.should_update():
            try:
                news_items = await self.fetch()
                
                # 更新自适应间隔
                self.update_adaptive_interval(len(news_items))
                
                return news_items
            except Exception as e:
                logger.error(f"Error fetching news from {self.source_id}: {str(e)}")
                return []
        else:
            logger.debug(f"Skipping update for {self.source_id}, next update in {self.adaptive_interval - (time.time() - self.last_update_time)}s")
            return [] 