import asyncio
import datetime
import hashlib
import logging
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

import aiohttp
import feedparser
from bs4 import BeautifulSoup

from worker.sources.base import NewsSource, NewsItemModel
from worker.utils.http_client import http_client

logger = logging.getLogger(__name__)


class RSSNewsSource(NewsSource):
    """
    RSS新闻源适配器
    支持从RSS feed获取新闻
    """
    
    def __init__(
        self,
        source_id: str,
        name: str,
        feed_url: str,
        update_interval: int = 1800,  # 默认30分钟更新一次
        cache_ttl: int = 600,  # 默认缓存10分钟
        category: Optional[str] = None,
        country: Optional[str] = None,
        language: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            source_id=source_id,
            name=name,
            update_interval=update_interval,
            cache_ttl=cache_ttl,
            category=category,
            country=country,
            language=language,
            config=config
        )
        self.feed_url = feed_url
        self.max_items = config.get("max_items", 20) if config else 20
        self.fetch_content = config.get("fetch_content", False) if config else False
        self.content_selector = config.get("content_selector") if config else None
        self.image_selector = config.get("image_selector") if config else None
        self.user_agent = config.get("user_agent", "HeatLink News Aggregator") if config else "HeatLink News Aggregator"
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从RSS feed获取新闻
        """
        logger.info(f"Fetching news from RSS feed: {self.feed_url}")
        
        try:
            # 获取RSS内容
            response = await http_client.fetch(
                url=self.feed_url,
                method="GET",
                headers={"User-Agent": self.user_agent},
                response_type="text"
            )
            
            # 解析RSS
            feed = feedparser.parse(response)
            
            if not feed.entries:
                logger.warning(f"No entries found in RSS feed: {self.feed_url}")
                return []
            
            # 处理条目
            news_items = []
            for entry in feed.entries[:self.max_items]:
                try:
                    # 生成唯一ID
                    entry_id = entry.get('id') or entry.get('link')
                    if not entry_id:
                        continue
                    
                    item_id = hashlib.md5(f"{self.source_id}:{entry_id}".encode()).hexdigest()
                    
                    # 获取发布时间
                    published_at = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        published_at = datetime.datetime(*entry.published_parsed[:6])
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        published_at = datetime.datetime(*entry.updated_parsed[:6])
                    
                    # 获取内容
                    content = ""
                    summary = ""
                    
                    if hasattr(entry, 'content') and entry.content:
                        content = entry.content[0].value
                    elif hasattr(entry, 'summary') and entry.summary:
                        content = entry.summary
                    elif hasattr(entry, 'description') and entry.description:
                        content = entry.description
                    
                    # 提取纯文本摘要
                    if content:
                        text_content = await self.extract_text_from_html(content)
                        summary = await self.generate_summary(text_content)
                    
                    # 获取图片URL
                    image_url = None
                    
                    # 从媒体内容中获取
                    if hasattr(entry, 'media_content') and entry.media_content:
                        for media in entry.media_content:
                            if 'url' in media and media.get('medium', '') in ['image', '']:
                                image_url = media['url']
                                break
                    
                    # 从媒体缩略图中获取
                    if not image_url and hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
                        for thumbnail in entry.media_thumbnail:
                            if 'url' in thumbnail:
                                image_url = thumbnail['url']
                                break
                    
                    # 从内容中提取图片
                    if not image_url and content:
                        soup = BeautifulSoup(content, 'html.parser')
                        img_tag = soup.find('img')
                        if img_tag and img_tag.get('src'):
                            image_url = img_tag.get('src')
                    
                    # 如果配置了获取完整内容，则获取文章页面
                    if self.fetch_content:
                        try:
                            full_content = await self._fetch_full_content(entry.link)
                            if full_content:
                                content = full_content
                                # 重新生成摘要
                                text_content = await self.extract_text_from_html(content)
                                summary = await self.generate_summary(text_content)
                                
                                # 如果没有图片，尝试从完整内容中提取
                                if not image_url:
                                    soup = BeautifulSoup(content, 'html.parser')
                                    if self.image_selector:
                                        img_tag = soup.select_one(self.image_selector)
                                    else:
                                        img_tag = soup.find('img')
                                    
                                    if img_tag and img_tag.get('src'):
                                        image_url = img_tag.get('src')
                        except Exception as e:
                            logger.error(f"Error fetching full content for {entry.link}: {str(e)}")
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=item_id,
                        title=entry.title,
                        url=entry.link,
                        content=content,
                        summary=summary,
                        image_url=image_url,
                        published_at=published_at,
                        extra={
                            "source_id": self.source_id,
                            "source_name": self.name,
                            "category": self.category,
                            "author": entry.get('author', ''),
                            "tags": [tag.term for tag in entry.get('tags', [])] if hasattr(entry, 'tags') else [],
                            "mobile_url": None,  # RSS通常不提供移动版URL
                            "is_top": False
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing RSS entry: {str(e)}")
                    continue
            
            logger.info(f"Fetched {len(news_items)} news items from RSS feed: {self.feed_url}")
            return news_items
        
        except Exception as e:
            logger.error(f"Error fetching RSS feed {self.feed_url}: {str(e)}")
            raise
    
    async def _fetch_full_content(self, url: str) -> Optional[str]:
        """
        获取文章完整内容
        """
        try:
            response = await http_client.fetch(
                url=url,
                method="GET",
                headers={"User-Agent": self.user_agent},
                response_type="text"
            )
            
            soup = BeautifulSoup(response, 'html.parser')
            
            # 使用选择器提取内容
            if self.content_selector:
                content_element = soup.select_one(self.content_selector)
                if content_element:
                    return str(content_element)
            
            # 尝试常见的内容容器
            for selector in [
                'article', 
                '.article', 
                '.post-content', 
                '.entry-content', 
                '.content', 
                '#content',
                '.article-content',
                '.story-body'
            ]:
                content_element = soup.select_one(selector)
                if content_element:
                    return str(content_element)
            
            # 如果没有找到内容容器，返回None
            return None
        
        except Exception as e:
            logger.error(f"Error fetching full content from {url}: {str(e)}")
            return None

    async def close(self):
        """
        关闭资源
        """
        # 调用父类的close方法
        await super().close()


class RSSSourceFactory:
    """
    RSS新闻源工厂
    用于创建常见RSS新闻源
    """
    
    @staticmethod
    def create_source(
        source_id: str,
        name: str,
        feed_url: str,
        **kwargs
    ) -> RSSNewsSource:
        """
        创建RSS新闻源
        """
        return RSSNewsSource(
            source_id=source_id,
            name=name,
            feed_url=feed_url,
            **kwargs
        )
    
    @staticmethod
    def create_zhihu_daily() -> RSSNewsSource:
        """
        创建知乎日报新闻源
        """
        return RSSNewsSource(
            source_id="zhihu_daily",
            name="知乎日报",
            feed_url="https://rsshub.app/zhihu/daily",
            category="knowledge",
            country="CN",
            language="zh-CN",
            update_interval=3600,  # 1小时更新一次
            config={
                "fetch_content": True,
                "content_selector": ".content"
            }
        )
    
    @staticmethod
    def create_hacker_news() -> RSSNewsSource:
        """
        创建Hacker News新闻源
        """
        return RSSNewsSource(
            source_id="hacker_news",
            name="Hacker News",
            feed_url="https://news.ycombinator.com/rss",
            category="technology",
            country="US",
            language="en",
            update_interval=1800,  # 30分钟更新一次
            config={
                "fetch_content": True
            }
        )
    
    @staticmethod
    def create_bbc_news() -> RSSNewsSource:
        """
        创建BBC新闻源
        """
        return RSSNewsSource(
            source_id="bbc_news",
            name="BBC News",
            feed_url="http://feeds.bbci.co.uk/news/world/rss.xml",
            category="news",
            country="GB",
            language="en",
            update_interval=1800,  # 30分钟更新一次
            config={
                "fetch_content": True,
                "content_selector": ".story-body__inner"
            }
        ) 