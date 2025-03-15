import asyncio
import datetime
import hashlib
import json
import logging
import re
from abc import abstractmethod
from typing import List, Dict, Any, Optional, Tuple, Union

import aiohttp
from bs4 import BeautifulSoup

from worker.sources.base import NewsSource, NewsItemModel
from worker.utils.http_client import http_client

logger = logging.getLogger(__name__)


class WebNewsSource(NewsSource):
    """
    网页抓取新闻源适配器基类
    用于处理需要从网页抓取数据的新闻源
    """
    
    def __init__(
        self,
        source_id: str,
        name: str,
        url: str,
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "general",
        country: str = "global",
        language: str = "en",
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
        self.url = url
        self.headers = self.config.get("headers", {})
        self._http_client = None
        
        # 重试配置
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 2)
        self.retry_backoff = self.config.get("retry_backoff", 2)
        self.retry_status_codes = self.config.get("retry_status_codes", [429, 500, 502, 503, 504])
        
        # 如果没有设置User-Agent，则添加默认值
        if "User-Agent" not in self.headers:
            self.headers["User-Agent"] = self.config.get("user_agent", "HeatLink News Aggregator")
    
    @property
    async def http_client(self) -> aiohttp.ClientSession:
        """
        获取HTTP客户端
        """
        if self._http_client is None or self._http_client.closed:
            self._http_client = aiohttp.ClientSession()
        return self._http_client
    
    async def close(self):
        """
        关闭HTTP客户端
        """
        if self._http_client and not self._http_client.closed:
            await self._http_client.close()
    
    async def fetch_content(self) -> str:
        """
        获取网页内容
        """
        client = await self.http_client
        
        # 实现智能重试
        retry_count = 0
        current_delay = self.retry_delay
        
        while retry_count <= self.max_retries:
            try:
                async with client.get(self.url, headers=self.headers, timeout=30) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status in self.retry_status_codes and retry_count < self.max_retries:
                        # 需要重试的状态码
                        retry_count += 1
                        logger.warning(f"Received status {response.status} from {self.url}, retrying ({retry_count}/{self.max_retries})...")
                        await asyncio.sleep(current_delay)
                        current_delay *= self.retry_backoff  # 指数退避
                    else:
                        logger.error(f"Failed to fetch content from {self.url}, status: {response.status}")
                        return ""
            except asyncio.TimeoutError:
                if retry_count < self.max_retries:
                    retry_count += 1
                    logger.warning(f"Timeout when fetching {self.url}, retrying ({retry_count}/{self.max_retries})...")
                    await asyncio.sleep(current_delay)
                    current_delay *= self.retry_backoff
                else:
                    logger.error(f"Timeout when fetching {self.url} after {self.max_retries} retries")
                    return ""
            except Exception as e:
                if retry_count < self.max_retries:
                    retry_count += 1
                    logger.warning(f"Error fetching {self.url}: {str(e)}, retrying ({retry_count}/{self.max_retries})...")
                    await asyncio.sleep(current_delay)
                    current_delay *= self.retry_backoff
                else:
                    logger.error(f"Error fetching {self.url} after {self.max_retries} retries: {str(e)}")
                    return ""
        
        return ""
    
    @abstractmethod
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析响应内容
        子类必须实现此方法
        """
        pass
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从网页抓取新闻
        """
        logger.info(f"Fetching news from web: {self.url}")
        
        try:
            # 获取网页内容
            content = await self.fetch_content()
            if not content:
                return []
            
            # 解析响应
            news_items = await self.parse_response(content)
            
            logger.info(f"Fetched {len(news_items)} news items from web: {self.url}")
            return news_items
        
        except Exception as e:
            logger.error(f"Error fetching web news from {self.url}: {str(e)}")
            raise
    
    def extract_json_from_html(self, html: str, pattern: str) -> Optional[Dict[str, Any]]:
        """
        从HTML中提取JSON数据
        pattern: 正则表达式，用于匹配JSON数据
        """
        try:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                json_str = match.group(1)
                return json.loads(json_str)
            return None
        except Exception as e:
            logger.error(f"Error extracting JSON from HTML: {str(e)}")
            return None
    
    def generate_id(self, unique_str: str) -> str:
        """
        生成唯一ID
        """
        return hashlib.md5(f"{self.source_id}:{unique_str}".encode()).hexdigest()
    
    def parse_date(self, date_str: str, format_str: Optional[str] = None) -> Optional[datetime.datetime]:
        """
        解析日期字符串
        """
        if not date_str:
            return None
        
        try:
            if format_str:
                return datetime.datetime.strptime(date_str, format_str)
            
            # 尝试常见的日期格式
            for fmt in [
                "%Y-%m-%dT%H:%M:%S.%fZ",  # ISO 8601 with microseconds
                "%Y-%m-%dT%H:%M:%SZ",      # ISO 8601
                "%Y-%m-%d %H:%M:%S",       # 常见格式
                "%Y/%m/%d %H:%M:%S",       # 常见格式
                "%Y年%m月%d日 %H:%M:%S",   # 中文格式
                "%Y年%m月%d日 %H:%M",      # 中文格式
                "%Y-%m-%d",                # 仅日期
                "%Y/%m/%d",                # 仅日期
                "%Y年%m月%d日",            # 中文仅日期
            ]:
                try:
                    return datetime.datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            
            # 尝试解析时间戳
            try:
                timestamp = float(date_str)
                return datetime.datetime.fromtimestamp(timestamp)
            except ValueError:
                pass
            
            logger.warning(f"Could not parse date: {date_str}")
            return None
        
        except Exception as e:
            logger.error(f"Error parsing date {date_str}: {str(e)}")
            return None


class APINewsSource(WebNewsSource):
    """
    API新闻源适配器基类
    用于处理需要从API获取数据的新闻源
    """
    
    def __init__(
        self,
        source_id: str,
        name: str,
        api_url: str,
        update_interval: int = 600,
        cache_ttl: int = 300,
        category: Optional[str] = None,
        country: Optional[str] = None,
        language: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            source_id=source_id,
            name=name,
            url=api_url,
            update_interval=update_interval,
            cache_ttl=cache_ttl,
            category=category,
            country=country,
            language=language,
            config=config
        )
        self.api_url = api_url
        self.params = config.get("params", {}) if config else {}
        self.json_data = config.get("json_data", {}) if config else {}
        self.response_type = config.get("response_type", "json") if config else "json"
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从API获取新闻
        """
        logger.info(f"Fetching news from API: {self.api_url}")
        
        try:
            # 获取API响应
            response = await http_client.fetch(
                url=self.api_url,
                method="GET",
                headers=self.headers,
                params=self.params,
                json_data=self.json_data,
                response_type=self.response_type
            )
            
            # 解析响应
            news_items = await self.parse_response(response)
            
            logger.info(f"Fetched {len(news_items)} news items from API: {self.api_url}")
            return news_items
        
        except Exception as e:
            logger.error(f"Error fetching API news from {self.api_url}: {str(e)}")
            raise 