import json
import uuid
import time
import logging
import asyncio
import hashlib
import datetime
import re
import urllib.parse
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union, Tuple, Set

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
        
        # 添加超时控制
        self.connect_timeout = self.config.get("connect_timeout", 10)  # 连接超时（秒）
        self.read_timeout = self.config.get("read_timeout", 30)  # 读取超时（秒）
        self.total_timeout = self.config.get("total_timeout", 60)  # 总超时（秒）
        
        # 添加代理支持
        self.proxy = self.config.get("proxy", None)  # 单个代理
        self.proxies = self.config.get("proxies", [])  # 代理列表
        self.current_proxy_index = 0
        
        # 添加用户代理轮换
        self.user_agents = self.config.get("user_agents", [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
        ])
        self.current_ua_index = 0
        
        # 添加重试配置
        self.max_retries = self.config.get("max_retries", 3)  # 最大重试次数
        self.retry_delay = self.config.get("retry_delay", 2)  # 重试延迟（秒）
        
        # 添加缓存配置
        self.use_memory_cache = self.config.get("use_memory_cache", True)
        self.use_persistent_cache = self.config.get("use_persistent_cache", False)
        
        # 添加日志配置
        self.log_requests = self.config.get("log_requests", False)
        self.log_responses = self.config.get("log_responses", False)
        
        # 添加性能监控
        self.performance_metrics = []
        
        # 添加内容去重
        self.title_hashes = set()  # 用于存储标题哈希值
    
    @property
    def http_client(self) -> aiohttp.ClientSession:
        """
        获取HTTP客户端
        """
        if self._http_client is None or self._http_client.closed:
            headers = {
                "User-Agent": self.get_next_user_agent()
            }
            
            # 合并配置中的headers
            if "headers" in self.config:
                headers.update(self.config["headers"])
            
            self._http_client = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(
                    connect=self.connect_timeout,
                    sock_read=self.read_timeout,
                    total=self.total_timeout
                )
                # 注意：aiohttp.ClientSession不接受proxy参数
                # 代理应该在请求时通过proxy参数传递
            )
        return self._http_client
    
    def get_next_proxy(self) -> Optional[str]:
        """
        获取下一个代理
        """
        if self.proxy:
            return self.proxy
        
        if not self.proxies:
            return None
        
        proxy = self.proxies[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
        return proxy
    
    def get_next_user_agent(self) -> str:
        """
        获取下一个用户代理
        """
        if not self.user_agents:
            return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        
        ua = self.user_agents[self.current_ua_index]
        self.current_ua_index = (self.current_ua_index + 1) % len(self.user_agents)
        return ua
    
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
    
    async def fetch_with_retry(self, url: str, method: str = "GET", headers: Dict[str, Any] = None, 
                              data: Any = None, params: Dict[str, Any] = None, 
                              response_type: str = "text", **kwargs) -> Any:
        """
        带重试的请求
        """
        start_time = time.time()
        
        # 记录请求信息
        if self.log_requests:
            logger.debug(f"Request: {method} {url}")
            if headers:
                logger.debug(f"Headers: {headers}")
            if params:
                logger.debug(f"Params: {params}")
            if data:
                logger.debug(f"Data: {data}")
        
        # 创建HTTP客户端
        client = await self.http_client
        
        # 重试逻辑
        for retry in range(self.max_retries):
            try:
                # 发送请求
                async with client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=data,
                    params=params,
                    proxy=self.get_next_proxy(),  # 添加代理参数
                    **kwargs
                ) as response:
                    # 记录响应信息
                    if self.log_responses:
                        logger.debug(f"Response: {response.status} {response.reason}")
                        logger.debug(f"Response headers: {response.headers}")
                    
                    # 检查响应状态
                    if not response.ok:
                        # 特殊处理某些状态码
                        if response.status == 429:  # Too Many Requests
                            retry_after = int(response.headers.get('Retry-After', self.retry_delay * (retry + 1)))
                            logger.warning(f"Rate limited, retrying after {retry_after}s")
                            await asyncio.sleep(retry_after)
                            continue
                        
                        if response.status == 403:  # Forbidden
                            # 尝试更换代理和用户代理
                            self._http_client = None  # 强制创建新的会话
                            logger.warning(f"Forbidden, changing proxy and user agent")
                            if retry < self.max_retries - 1:
                                await asyncio.sleep(self.retry_delay * (retry + 1))
                                continue
                        
                        # 其他错误状态码
                        error_text = await response.text()
                        logger.error(f"HTTP error: {response.status} {response.reason}, {error_text[:200]}")
                        response.raise_for_status()
                    
                    # 处理不同类型的响应
                    if response_type == "json":
                        result = await response.json()
                    elif response_type == "bytes":
                        result = await response.read()
                    else:  # 默认为text
                        result = await response.text()
                    
                    # 记录性能指标
                    end_time = time.time()
                    self.record_performance(f"{method} {url}", start_time, end_time)
                    
                    return result
            
            except aiohttp.ClientConnectorError as e:
                logger.error(f"Connection error: {str(e)}")
                if retry < self.max_retries - 1:
                    # 尝试更换代理
                    self._http_client = None  # 强制创建新的会话
                    await asyncio.sleep(self.retry_delay * (retry + 1))
                else:
                    raise
            
            except aiohttp.ClientResponseError as e:
                logger.error(f"Response error: {str(e)}")
                if retry < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (retry + 1))
                else:
                    raise
            
            except asyncio.TimeoutError:
                logger.error(f"Timeout error for {url}")
                if retry < self.max_retries - 1:
                    # 增加超时时间
                    self.read_timeout = min(self.read_timeout * 1.5, 120)
                    self.total_timeout = min(self.total_timeout * 1.5, 180)
                    self._http_client = None  # 强制创建新的会话
                    await asyncio.sleep(self.retry_delay * (retry + 1))
                else:
                    raise
            
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                if retry < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (retry + 1))
                else:
                    raise
    
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
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def create_news_item(self, **kwargs) -> NewsItemModel:
        """
        创建标准化的NewsItemModel实例，确保source_id和source_name正确设置
        
        这个辅助方法可以被所有数据源使用，以确保数据格式的一致性
        """
        # 确保source_id和source_name设置在主体字段中，而不是extra字段中
        if 'source_id' not in kwargs:
            kwargs['source_id'] = self.source_id
        
        if 'source_name' not in kwargs:
            kwargs['source_name'] = self.name
        
        # 如果extra字段中包含source_id或source_name，将它们移除
        if 'extra' in kwargs and isinstance(kwargs['extra'], dict):
            if 'source_id' in kwargs['extra']:
                kwargs['extra'].pop('source_id')
            if 'source_name' in kwargs['extra']:
                kwargs['extra'].pop('source_name')
        
        # 清洗标题和URL
        if 'title' in kwargs:
            kwargs['title'] = self.clean_title(kwargs['title'])
        
        if 'url' in kwargs:
            kwargs['url'] = self.clean_url(kwargs['url'])
        
        # 创建NewsItemModel实例
        return NewsItemModel(**kwargs)
    
    def clean_title(self, title: str) -> str:
        """
        清洗标题
        """
        if not title:
            return ""
        
        # 移除多余空白字符
        title = re.sub(r'\s+', ' ', title).strip()
        
        # 移除特殊字符
        title = re.sub(r'[\x00-\x1F\x7F]', '', title)
        
        # 移除广告标记
        ad_patterns = [r'\[广告\]', r'\[AD\]', r'\[推广\]', r'\[赞助\]']
        for pattern in ad_patterns:
            title = re.sub(pattern, '', title, flags=re.IGNORECASE)
        
        return title
    
    def clean_url(self, url: str) -> str:
        """
        清洗URL
        """
        if not url:
            return ""
        
        try:
            # 移除跟踪参数
            parsed_url = urllib.parse.urlparse(url)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            
            # 移除常见的跟踪参数
            tracking_params = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
                              'source', 'from', 'ref', 'referrer', 'track']
            for param in tracking_params:
                if param in query_params:
                    del query_params[param]
            
            # 重建URL
            clean_query = urllib.parse.urlencode(query_params, doseq=True)
            clean_url = urllib.parse.urlunparse((
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                parsed_url.params,
                clean_query,
                parsed_url.fragment
            ))
            
            return clean_url
        except Exception as e:
            logger.warning(f"Error cleaning URL {url}: {str(e)}")
            return url
    
    def is_duplicate(self, title: str) -> bool:
        """
        检查标题是否重复
        """
        if not title:
            return False
        
        title_hash = hashlib.md5(title.encode('utf-8')).hexdigest()
        if title_hash in self.title_hashes:
            return True
        
        self.title_hashes.add(title_hash)
        return False
    
    def record_performance(self, operation: str, start_time: float, end_time: float) -> None:
        """
        记录性能指标
        """
        elapsed_time = end_time - start_time
        self.performance_metrics.append({
            "operation": operation,
            "elapsed_time": elapsed_time,
            "timestamp": time.time()
        })
        
        # 保留最近100条记录
        if len(self.performance_metrics) > 100:
            self.performance_metrics = self.performance_metrics[-100:]
        
        logger.debug(f"Performance: {operation} took {elapsed_time:.2f}s")
    
    def get_cache_key(self, params: Dict[str, Any] = None) -> str:
        """
        生成缓存键
        """
        key_parts = [self.source_id]
        if params:
            for k, v in sorted(params.items()):
                key_parts.append(f"{k}={v}")
        return ":".join(key_parts)
    
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
    
    def update_adaptive_interval(self, news_count: int, success: bool = True) -> None:
        """
        更新自适应间隔
        根据新闻数量动态调整更新频率
        
        策略：
        1. 如果新闻数量增加，减少更新间隔
        2. 如果新闻数量减少或不变，增加更新间隔
        3. 保持在最小和最大间隔之间
        4. 考虑成功率和一天中的时间
        """
        current_time = time.time()
        
        # 记录本次更新
        self.update_history.append({
            "time": current_time,
            "count": news_count,
            "success": success
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
            
            # 计算成功率
            success_count = sum(1 for record in self.update_history if record.get("success", True))
            success_rate = success_count / len(self.update_history)
            
            # 根据多种因素调整间隔
            if avg_growth_rate > 0.1:  # 快速增长
                # 减少间隔，但考虑成功率
                factor = 0.8 if success_rate > 0.8 else 0.9
                self.adaptive_interval = max(self.min_update_interval, self.adaptive_interval * factor)
            elif avg_growth_rate < 0:  # 减少或不变
                # 增加间隔，但考虑成功率
                factor = 1.2 if success_rate > 0.8 else 1.1
                self.adaptive_interval = min(self.max_update_interval, self.adaptive_interval * factor)
            
            # 考虑一天中的时间
            hour = datetime.datetime.now().hour
            if 8 <= hour <= 22:  # 白天
                # 白天更频繁更新
                self.adaptive_interval = max(self.min_update_interval, self.adaptive_interval * 0.9)
            else:  # 夜间
                # 夜间减少更新频率
                self.adaptive_interval = min(self.max_update_interval, self.adaptive_interval * 1.1)
            
            logger.debug(f"Source {self.source_id} adaptive interval updated to {self.adaptive_interval:.2f}s")
        
        # 更新最后更新时间和数量
        self.last_update_time = current_time
        self.last_update_count = news_count
    
    async def get_news(self, force_update: bool = False) -> List[NewsItemModel]:
        """
        获取新闻，支持强制更新
        """
        start_time = time.time()
        
        if force_update or self.should_update():
            try:
                news_items = await self.fetch()
                
                # 过滤重复内容
                unique_items = []
                for item in news_items:
                    if not self.is_duplicate(item.title):
                        unique_items.append(item)
                
                # 更新自适应间隔
                self.update_adaptive_interval(len(unique_items), success=True)
                
                # 记录性能指标
                end_time = time.time()
                self.record_performance(f"get_news({self.source_id})", start_time, end_time)
                
                return unique_items
            except Exception as e:
                logger.error(f"Error fetching news from {self.source_id}: {str(e)}")
                
                # 更新自适应间隔（失败）
                self.update_adaptive_interval(0, success=False)
                
                # 记录性能指标
                end_time = time.time()
                self.record_performance(f"get_news({self.source_id}) [ERROR]", start_time, end_time)
                
                return []
        else:
            logger.debug(f"Skipping update for {self.source_id}, next update in {self.adaptive_interval - (time.time() - self.last_update_time):.2f}s")
            return [] 