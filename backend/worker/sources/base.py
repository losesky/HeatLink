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
from worker.sources.interface import NewsSourceInterface
from worker.utils.proxy_manager import proxy_manager

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
        self.priority = 0  # 默认优先级为0
        
        # 自适应调度相关属性
        self.min_update_interval = 120  # 最小更新间隔(秒)，默认2分钟
        self.max_update_interval = 7200  # 最大更新间隔(秒)，默认2小时
        self.adaptive_interval = update_interval  # 当前的自适应间隔
        self.last_update_time = 0  # 上次更新时间(时间戳)
        self.last_update_count = 0  # 上次更新获取的新闻数量
        self.update_history = []  # 更新历史记录
        self.max_history_size = 10  # 保存的历史记录数量
        self.history_fingerprints = set()  # 用于去重的历史指纹
        self.enable_adaptive = True  # 是否启用自适应调度
        self.performance_metrics = {}  # 性能指标记录
        
        # 初始化重试相关属性
        self.max_retries = 3  # 最大重试次数
        self.retry_delay = 5  # 重试延迟(秒)
        self.error_count = 0  # 连续错误计数
        self.last_error = None  # 最后一次错误信息
        
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
        
        # 添加缓存配置
        self.use_memory_cache = self.config.get("use_memory_cache", True)
        self.use_persistent_cache = self.config.get("use_persistent_cache", False)
        
        # 添加日志配置
        self.log_requests = self.config.get("log_requests", False)
        self.log_responses = self.config.get("log_responses", False)
        
        # 添加代理配置 - 数据库中的配置，优先级高于代码中的配置
        self.need_proxy = self.config.get("need_proxy", False)  # 是否需要代理
        self.proxy_fallback = self.config.get("proxy_fallback", True)  # 代理失败是否尝试直连
        self.proxy_group = self.config.get("proxy_group", "default")  # 使用的代理组
        
        # 固定需要代理的源列表
        self.proxy_required_sources = [
            "github", "bloomberg-markets", "bloomberg-tech", "bloomberg", 
            "hackernews", "bbc_world", "bloomberg-china", "v2ex", "producthunt"
        ]
        
        # 如果该源ID在需要代理的列表中，自动设置need_proxy为True
        if self.source_id in self.proxy_required_sources or any(s in self.source_id for s in self.proxy_required_sources):
            self.need_proxy = True
    
    @property
    async def http_client(self) -> aiohttp.ClientSession:
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
    
    async def get_next_proxy(self) -> Optional[Dict[str, Any]]:
        """
        获取下一个代理URL和配置
        优先使用代理管理器，如果不可用则回退到类属性中的代理
        """
        # 如果不需要代理，直接返回None
        if not self.need_proxy:
            return None
            
        # 尝试从代理管理器获取代理
        try:
            proxy_config = await proxy_manager.get_proxy(self.source_id, self.proxy_group)
            if proxy_config:
                logger.info(f"为 {self.source_id} 使用代理管理器提供的代理: {proxy_config['host']}:{proxy_config['port']}")
                return proxy_config
        except Exception as e:
            logger.warning(f"从代理管理器获取代理失败: {e}，将尝试使用配置的代理")
        
        # 如果代理管理器不可用或未返回代理，使用配置的代理
        if self.proxy:
            return {"url": self.proxy, "id": None}
        
        if not self.proxies:
            logger.warning(f"数据源 {self.source_id} 需要代理但未找到可用代理")
            return None
        
        proxy = self.proxies[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
        return {"url": proxy, "id": None}
    
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
        执行HTTP请求，自动重试
        
        Args:
            url: 请求URL
            method: 请求方法 (GET, POST等)
            headers: 请求头
            data: 请求数据
            params: 请求参数
            response_type: 响应类型 (text, json, bytes)
            **kwargs: 其他参数
            
        Returns:
            响应内容
        """
        # 尝试导入安全HTTP请求模块
        try:
            from backend.worker.asyncio_fix.http_helper import safe_request
            
            # 使用安全HTTP请求函数
            return_json = response_type.lower() == 'json'
            timeout = kwargs.get('timeout', 30.0)
            max_retries = kwargs.get('max_retries', 3)
            retry_delay = kwargs.get('retry_delay', 1.0)
            verify_ssl = kwargs.get('verify_ssl', True)
            
            # 获取代理配置
            proxy_config = await self.get_next_proxy()
            user_agent = self.get_next_user_agent()
            
            start_time = time.time()
            proxy_used = False
            
            # 如果需要代理则先尝试使用代理
            if self.need_proxy and proxy_config:
                proxy = proxy_config.get("url")
                proxy_used = True
                try:
                    logger.info(f"使用代理 {proxy} 请求 {url}")
                    # 执行请求（使用代理）
                    success, result, error_message = await safe_request(
                        url=url,
                        method=method,
                        headers=headers,
                        params=params,
                        data=data,
                        timeout=timeout,
                        max_retries=max_retries,
                        retry_delay=retry_delay,
                        return_json=return_json,
                        verify_ssl=verify_ssl,
                        user_agent=user_agent,
                        proxy=proxy,
                        verbose=kwargs.get('verbose', False)
                    )
                    
                    elapsed = time.time() - start_time
                    # 向代理管理器报告代理状态
                    if hasattr(proxy_manager, 'report_proxy_status') and proxy_used:
                        await proxy_manager.report_proxy_status(proxy_config.get('id'), success, elapsed)
                    
                    if success:
                        logger.info(f"通过代理成功请求 {url}，耗时: {elapsed:.2f}秒")
                        
                        # 根据response_type处理结果
                        if response_type.lower() == 'bytes' and isinstance(result, str):
                            return result.encode('utf-8')
                        
                        return result
                    else:
                        logger.warning(f"通过代理请求失败: {error_message}")
                        # 如果代理失败且允许回退到直连，则继续执行
                        if not self.proxy_fallback:
                            raise Exception(f"请求失败: {error_message}")
                except Exception as e:
                    logger.warning(f"通过代理请求出错: {e}")
                    # 如果不允许回退到直连，则直接抛出异常
                    if not self.proxy_fallback:
                        raise
            
            # 如果没有代理，或代理失败且允许回退到直连，则尝试直连
            if not proxy_used or (proxy_used and self.proxy_fallback):
                logger.info(f"直连请求 {url}")
                success, result, error_message = await safe_request(
                    url=url,
                    method=method,
                    headers=headers,
                    params=params,
                    data=data,
                    timeout=timeout,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                    return_json=return_json,
                    verify_ssl=verify_ssl,
                    user_agent=user_agent,
                    proxy=None,
                    verbose=kwargs.get('verbose', False)
                )
                
                if not success:
                    raise Exception(f"请求失败: {error_message}")
                
                # 根据response_type处理结果
                if response_type.lower() == 'bytes' and isinstance(result, str):
                    return result.encode('utf-8')
                
                return result
        except ImportError:
            # 如果无法导入安全HTTP模块，使用原始实现
            import aiohttp
            import asyncio
            
            start_time = time.time()
            max_retries = kwargs.get('max_retries', 3)
            timeout = kwargs.get('timeout', 30)
            retry_count = 0
            last_exception = None
            
            while retry_count < max_retries:
                try:
                    # 设置超时
                    timeout_obj = aiohttp.ClientTimeout(total=timeout)
                    
                    # 获取代理配置
                    proxy_config = await self.get_next_proxy()
                    proxy = proxy_config.get("url") if proxy_config else None
                    
                    # 从用户代理池获取User-Agent
                    user_agent = self.get_next_user_agent()
                    
                    # 如果没有提供headers，则创建一个
                    if headers is None:
                        headers = {}
                    
                    # 如果headers中没有User-Agent，则添加
                    if 'User-Agent' not in headers:
                        headers['User-Agent'] = user_agent
                    
                    proxy_used = False
                    
                    # 如果需要代理则先尝试使用代理
                    if self.need_proxy and proxy:
                        proxy_used = True
                        try:
                            logger.info(f"使用代理 {proxy} 请求 {url}")
                            # 执行请求（使用代理）
                            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                                async with session.request(
                                    method, url, headers=headers, data=data, params=params, 
                                    proxy=proxy, ssl=kwargs.get('verify_ssl', True)
                                ) as response:
                                    # 检查响应状态
                                    if response.status >= 400:
                                        error_text = await response.text()
                                        logger.warning(f"通过代理请求响应状态码: {response.status}")
                                        # 如果不允许回退到直连，则抛出异常
                                        if not self.proxy_fallback:
                                            raise Exception(f"HTTP error {response.status}: {error_text[:500]}")
                                    else:
                                        # 报告代理成功
                                        elapsed = time.time() - start_time
                                        if hasattr(proxy_manager, 'report_proxy_status') and proxy_used:
                                            await proxy_manager.report_proxy_status(proxy_config.get('id'), True, elapsed)
                                        
                                        logger.info(f"通过代理成功请求 {url}，状态码: {response.status}")
                                        
                                        # 根据response_type返回不同类型的响应
                                        if response_type.lower() == 'json':
                                            return await response.json()
                                        elif response_type.lower() == 'bytes':
                                            return await response.read()
                                        else:
                                            return await response.text()
                        except Exception as e:
                            # 报告代理失败
                            if hasattr(proxy_manager, 'report_proxy_status') and proxy_used and proxy_config:
                                await proxy_manager.report_proxy_status(proxy_config.get('id'), False)
                                
                            logger.warning(f"通过代理请求出错: {e}")
                            # A如果不允许回退到直连，则抛出异常
                            if not self.proxy_fallback:
                                raise
                    
                    # 如果没有代理，或代理失败且允许回退到直连，则尝试直连
                    if not proxy_used or (proxy_used and self.proxy_fallback):
                        logger.info(f"直连请求 {url}")
                        # 执行请求（直连）
                        async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                            async with session.request(
                                method, url, headers=headers, data=data, params=params, 
                                ssl=kwargs.get('verify_ssl', True)
                            ) as response:
                                # 检查响应状态
                                if response.status >= 400:
                                    error_text = await response.text()
                                    raise Exception(f"HTTP error {response.status}: {error_text[:500]}")
                                
                                # 根据response_type返回不同类型的响应
                                if response_type.lower() == 'json':
                                    return await response.json()
                                elif response_type.lower() == 'bytes':
                                    return await response.read()
                                else:
                                    return await response.text()
                
                except (aiohttp.ClientError, asyncio.TimeoutError, Exception) as e:
                    last_exception = e
                    retry_count += 1
                    if retry_count < max_retries:
                        # 计算等待时间（指数退避）
                        wait_time = 2 ** retry_count + random.uniform(0, 1)
                        logger.warning(f"请求 {url} 失败: {str(e)}. 将在 {wait_time:.2f} 秒后重试 ({retry_count}/{max_retries})")
                        await asyncio.sleep(wait_time)
                    else:
                        break
            
            # 记录性能数据
            end_time = time.time()
            operation_name = f"HTTP-{method}"
            self.record_performance(operation_name, start_time, end_time)
            
            # 所有重试都失败了
            raise Exception(f"请求 {url} 失败，已重试 {max_retries} 次: {str(last_exception)}")
    
    def generate_id(self, url: str, title: str = "", published_at: Optional[datetime.datetime] = None) -> str:
        """
        生成唯一ID
        
        Args:
            url: 文章URL
            title: 文章标题
            published_at: 发布时间
            
        Returns:
            唯一ID
        """
        # 创建一个唯一字符串
        unique_str = f"{self.source_id}:{url}"
        if title:
            unique_str += f":{title}"
        if published_at:
            unique_str += f":{published_at.isoformat()}"
        
        # 生成哈希
        return hashlib.md5(unique_str.encode('utf-8')).hexdigest()
    
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
        if title_hash in self.history_fingerprints:
            return True
        
        self.history_fingerprints.add(title_hash)
        
        # 如果历史记录过大，删除旧记录
        if len(self.history_fingerprints) > 1000:
            self.history_fingerprints = set(list(self.history_fingerprints)[-500:])
        
        return False
    
    def record_performance(self, operation: str, start_time: float, end_time: float):
        """
        记录性能指标
        
        Args:
            operation: 操作名称
            start_time: 开始时间
            end_time: 结束时间
        """
        duration = end_time - start_time
        
        if operation not in self.performance_metrics:
            self.performance_metrics[operation] = {
                'count': 0,
                'total_duration': 0,
                'average_duration': 0,
                'min_duration': float('inf'),
                'max_duration': 0
            }
        
        metrics = self.performance_metrics[operation]
        metrics['count'] += 1
        metrics['total_duration'] += duration
        metrics['average_duration'] = metrics['total_duration'] / metrics['count']
        metrics['min_duration'] = min(metrics['min_duration'], duration)
        metrics['max_duration'] = max(metrics['max_duration'], duration)
    
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
        基于自适应间隔和最后更新时间
        """
        current_time = time.time()
        
        # 如果从未更新或强制更新，则应该更新
        if self.last_update_time == 0:
            return True
        
        # 计算更新间隔
        interval = self.adaptive_interval if self.enable_adaptive else self.update_interval
        
        # 如果已经过了更新间隔，则应该更新
        return (current_time - self.last_update_time) >= interval
    
    def update_adaptive_interval(self, news_count: int, success: bool = True) -> None:
        """
        更新自适应间隔
        基于新闻数量、成功状态和更新频率计算
        """
        if not self.enable_adaptive:
            return
        
        current_time = time.time()
        
        # 添加本次更新记录
        if len(self.update_history) >= self.max_history_size:
            self.update_history.pop(0)
        
        self.update_history.append({
            "time": current_time,
            "count": news_count,
            "success": success
        })
        
        # 如果历史记录少于2条，不进行调整
        if len(self.update_history) < 2:
            return
        
        # 计算平均增长率
        avg_growth_rate = 0
        for i in range(1, len(self.update_history)):
            prev_record = self.update_history[i-1]
            curr_record = self.update_history[i]
            
            time_diff = curr_record["time"] - prev_record["time"]
            count_diff = curr_record["count"] - prev_record["count"]
            
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
                
                # 重置错误计数
                self.error_count = 0
                self.last_error = None
                
                # 记录性能指标
                end_time = time.time()
                self.record_performance(f"get_news({self.source_id})", start_time, end_time)
                
                return unique_items
            except Exception as e:
                logger.error(f"Error fetching news from {self.source_id}: {str(e)}")
                
                # 更新错误信息
                self.error_count += 1
                self.last_error = str(e)
                
                # 更新自适应间隔（失败）
                self.update_adaptive_interval(0, success=False)
                
                # 记录性能指标
                end_time = time.time()
                self.record_performance(f"get_news({self.source_id}) [ERROR]", start_time, end_time)
                
                return []
        else:
            logger.debug(f"Skipping update for {self.source_id}, next update in {self.adaptive_interval - (time.time() - self.last_update_time):.2f}s")
            return []
    
    # 实现接口中的方法
    def update_metrics(self, news_count: int, success: bool = True, error: Optional[Exception] = None) -> None:
        """
        更新性能指标
        
        Args:
            news_count: 获取的新闻数量
            success: 是否成功
            error: 错误信息
        """
        self.last_update_count = news_count
        self.last_update_time = time.time()
        
        # 更新自适应间隔
        if self.enable_adaptive:
            self.update_adaptive_interval(news_count, success)
        
        # 记录错误
        if not success and error:
            self.error_count += 1
            self.last_error = str(error)
        else:
            self.error_count = 0
            self.last_error = None
            
        # 更新历史记录
        self.update_history.append({
            "time": self.last_update_time,
            "count": news_count,
            "success": success,
            "error": str(error) if error else None
        })
        
        # 保持历史记录大小
        if len(self.update_history) > self.max_history_size:
            self.update_history = self.update_history[-self.max_history_size:] 