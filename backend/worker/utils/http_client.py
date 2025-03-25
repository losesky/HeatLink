import json
import logging
import asyncio
import threading
import functools
from typing import Any, Dict, Optional, Union

import aiohttp
from aiohttp import ClientSession, ClientTimeout
from aiocache import cached, Cache
from aiocache.serializers import JsonSerializer

from app.core.config import settings

# 加载缓存修复模块
try:
    from worker.utils.cache_fix import safe_cache_decorator
except ImportError:
    try:
        from backend.worker.utils.cache_fix import safe_cache_decorator
    except ImportError:
        try:
            from .cache_fix import safe_cache_decorator
        except ImportError:
            # 如果无法导入，创建一个简单的实现
            def safe_cache_decorator(decorator):
                return decorator

# 记录当前使用的线程和事件循环映射
_thread_eventloops = {}

# 保存原始的cached装饰器并应用修复
original_cached = cached
cached = safe_cache_decorator(cached)

# 修复导入路径
try:
    from worker.asyncio_fix import get_or_create_eventloop
except ImportError:
    try:
        from backend.worker.asyncio_fix import get_or_create_eventloop
    except ImportError:
        # 如果都导入不了，尝试相对导入
        try:
            from ..asyncio_fix import get_or_create_eventloop
        except ImportError:
            # 提供一个简单的后备实现
            def get_or_create_eventloop():
                try:
                    return asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    return loop

logger = logging.getLogger(__name__)

# 线程本地存储，用于存储每个线程的会话和事件循环
_thread_local = threading.local()

# 保存原始的TCPConnector创建方法
original_TCPConnector = aiohttp.TCPConnector

# 修复会话和连接器使用不同事件循环的问题
class SafeTCPConnector(aiohttp.TCPConnector):
    def __init__(self, *args, **kwargs):
        # 如果没有提供loop参数，添加当前事件循环
        current_thread_id = threading.get_ident()
        if 'loop' not in kwargs or kwargs['loop'] is None:
            try:
                # 尝试从线程映射中获取
                if current_thread_id in _thread_eventloops:
                    kwargs['loop'] = _thread_eventloops[current_thread_id]
                else:
                    # 创建并记录新循环
                    loop = get_or_create_eventloop()
                    _thread_eventloops[current_thread_id] = loop
                    kwargs['loop'] = loop
            except Exception as e:
                logger.warning(f"获取事件循环出错，使用默认: {str(e)}")
                kwargs['loop'] = get_or_create_eventloop()
        
        # 确保使用统一事件循环
        loop = kwargs['loop']
        if loop:
            _thread_eventloops[current_thread_id] = loop
        
        super().__init__(*args, **kwargs)

# 替换TCPConnector类
aiohttp.TCPConnector = SafeTCPConnector

# 保存原始的ClientSession创建方法
original_ClientSession = aiohttp.ClientSession

# 修复ClientSession的创建方法
class SafeClientSession(aiohttp.ClientSession):
    def __init__(self, *args, **kwargs):
        # 确保使用同一个事件循环
        current_thread_id = threading.get_ident()
        
        # 获取当前线程的事件循环
        if current_thread_id in _thread_eventloops:
            loop = _thread_eventloops[current_thread_id]
        else:
            loop = get_or_create_eventloop()
            _thread_eventloops[current_thread_id] = loop
        
        # 强制使用此事件循环
        kwargs['loop'] = loop
        
        # 如果没有提供connector，创建一个使用相同事件循环的connector
        if 'connector' not in kwargs or kwargs['connector'] is None:
            kwargs['connector'] = SafeTCPConnector(loop=loop, ssl=False)
        elif kwargs['connector'] is not None:
            # 检查并确保connector使用相同的事件循环
            connector = kwargs['connector']
            connector_loop = getattr(connector, '_loop', None)
            
            if connector_loop is not None and connector_loop != loop:
                # 如果连接器使用不同的事件循环，创建新的连接器
                logger.warning(f"检测到连接器使用不同的事件循环，正在创建新连接器")
                kwargs['connector'] = SafeTCPConnector(loop=loop, ssl=False)
        
        super().__init__(*args, **kwargs)
    
    async def close(self):
        """安全关闭会话"""
        try:
            return await super().close()
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                logger.warning(f"忽略ClientSession.close中的'Event loop is closed'错误: {str(e)}")
                return None
            raise

# 替换ClientSession类
aiohttp.ClientSession = SafeClientSession

class HTTPClient:
    """
    Async HTTP client with caching support
    """
    
    def __init__(self, timeout: int = 30):
        self.timeout = ClientTimeout(total=timeout)
        self.session = None
        # 记录该客户端是否启动了关闭处理
        self._closing = False
        # 保存当前线程ID
        self._creator_thread_id = threading.get_ident()
    
    async def _get_session(self) -> ClientSession:
        """
        获取或创建一个ClientSession
        确保每个线程/任务都有自己的会话并且使用正确的事件循环
        """
        # 1. 获取当前线程ID和事件循环
        current_thread_id = threading.get_ident()
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            # 如果没有运行中的事件循环，创建一个新的
            current_loop = get_or_create_eventloop()
            asyncio.set_event_loop(current_loop)
            
        # 存储当前线程的事件循环以便后续使用
        if not hasattr(_thread_local, 'event_loops'):
            _thread_local.event_loops = {}
        _thread_local.event_loops[current_thread_id] = current_loop
        
        # 2. 检查线程本地存储中是否有会话
        if not hasattr(_thread_local, 'sessions'):
            _thread_local.sessions = {}
            
        # 3. 检查现有会话是否有效并使用正确的事件循环
        if current_thread_id in _thread_local.sessions:
            session = _thread_local.sessions[current_thread_id]
            
            # 验证会话是否有效
            if not session.closed:
                # 检查是否使用同一个事件循环
                connector = session.connector
                if connector and getattr(connector, '_loop', None) == current_loop:
                    # 会话有效且使用正确的事件循环
                    return session
                else:
                    # 会话使用了不同的事件循环，需要关闭并创建新的
                    logger.debug(f"会话使用了不同的事件循环，创建新会话。线程ID: {current_thread_id}")
                    try:
                        # 先关闭现有会话
                        try:
                            if not session.closed:
                                await session.close()
                        except Exception as e:
                            logger.warning(f"关闭旧会话时出错: {str(e)}")
                    finally:
                        # 无论是否成功关闭，都从存储中移除
                        _thread_local.sessions.pop(current_thread_id, None)
        
        # 4. 如果需要，检查实例级会话
        if (self.session is not None and 
            not self.session.closed and 
            self._creator_thread_id == current_thread_id):
            
            connector = self.session.connector
            if connector and getattr(connector, '_loop', None) == current_loop:
                # 实例级会话有效且使用正确的事件循环
                _thread_local.sessions[current_thread_id] = self.session
                return self.session
            else:
                # 实例级会话使用了不同的事件循环，需要关闭
                try:
                    if not self.session.closed:
                        await self.session.close()
                except Exception as e:
                    logger.warning(f"关闭实例级会话时出错: {str(e)}")
                # 不使用实例级会话，继续创建新的
        
        # 5. 创建新会话，确保使用当前线程的事件循环
        try:
            # 创建新的连接器
            connector = SafeTCPConnector(
                ssl=False, 
                enable_cleanup_closed=True,
                loop=current_loop,
                keepalive_timeout=30
            )
            
            # 创建新的会话
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            session = SafeClientSession(
                connector=connector,
                timeout=self.timeout,
                headers=headers,
                loop=current_loop,
                trust_env=True
            )
            
            # 存储新会话
            _thread_local.sessions[current_thread_id] = session
            
            # 如果是创建者线程，也更新实例级会话
            if current_thread_id == self._creator_thread_id:
                self.session = session
                
            logger.debug(f"为线程 {current_thread_id} 创建了新的会话")
            return session
            
        except Exception as e:
            logger.error(f"创建HTTP会话时出错: {str(e)}")
            # 尝试退回到简单的会话创建
            try:
                import aiohttp
                session = aiohttp.ClientSession()
                _thread_local.sessions[current_thread_id] = session
                return session
            except Exception as e2:
                logger.error(f"创建备用HTTP会话时出错: {str(e2)}")
                raise
    
    async def close(self):
        """安全关闭HTTP会话"""
        if self._closing:
            return
            
        self._closing = True
        current_thread_id = threading.get_ident()
        
        # 1. 关闭线程本地会话
        if hasattr(_thread_local, 'sessions'):
            if current_thread_id in _thread_local.sessions:
                session = _thread_local.sessions[current_thread_id]
                if session and not session.closed:
                    try:
                        await session.close()
                        logger.debug(f"已关闭线程 {current_thread_id} 的HTTP会话")
                    except Exception as e:
                        if "Event loop is closed" not in str(e):
                            logger.warning(f"关闭线程会话出错: {str(e)}")
                _thread_local.sessions.pop(current_thread_id, None)
        
        # 2. 如果在创建者线程中，也关闭实例级会话
        if self._creator_thread_id == current_thread_id and self.session and not self.session.closed:
            try:
                await self.session.close()
                logger.debug("已关闭实例级HTTP会话")
            except Exception as e:
                if "Event loop is closed" not in str(e):
                    logger.warning(f"关闭实例级会话出错: {str(e)}")
            self.session = None
            
        self._closing = False
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()
    
    async def request(
        self, 
        method: str, 
        url: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送HTTP请求并返回响应
        自动处理会话管理和失败重试
        支持代理管理器
        """
        # 重试机制参数
        max_retries = kwargs.pop('max_retries', 2)
        retry_delay = kwargs.pop('retry_delay', 1)
        retry_count = 0
        
        # 响应解析方式
        response_type = kwargs.pop('response_type', 'json')
        
        # 代理相关参数
        source_id = kwargs.pop('source_id', None)
        proxy_group = kwargs.pop('proxy_group', 'default')
        need_proxy = kwargs.pop('need_proxy', False)
        proxy_fallback = kwargs.pop('proxy_fallback', True)
        
        # 如果设置了特定代理URL，则使用它，否则使用代理管理器
        proxy_url = kwargs.pop('proxy', None)
        proxy_config = None
        
        # 提取域名信息
        domain = "unknown"
        try:
            import urllib.parse
            domain = urllib.parse.urlparse(url).netloc
        except Exception:
            pass
        
        # 检查域名是否在默认需要代理的列表中
        proxy_required_domains = []
        try:
            # 尝试从配置中获取代理域名列表
            from app.core.config import settings
            proxy_required_domains = settings.proxy_domains
        except ImportError:
            # 如果无法导入设置，使用默认列表
            proxy_required_domains = [
                "github.com", "bloomberg.com", "hackernews.firebaseio.com", 
                "news.ycombinator.com", "bbc.com", "v2ex.com", "producthunt.com",
                "xueqiu.com", "stock.xueqiu.com", "news.google.com", "google.com",
                "bbc.co.uk", "fastbull.cn", "ft.com",
                "nytimes.com", "wsj.com", "forbes.com", "cnbc.com",
                "reuters.com", "cnbc.com", "economist.com", "feeds.bbci.co.uk", "bbci.co.uk"
            ]
        
        try:
            if domain and any(required_domain in domain for required_domain in proxy_required_domains):
                need_proxy = True
                logger.info(f"HTTPClient请求: 域名 {domain} 在需要代理的列表中，自动启用代理")
        except Exception as e:
            logger.warning(f"解析URL域名时出错: {str(e)}")
        
        # 进一步详细记录代理参数
        logger.info(f"HTTPClient请求: {method} {url}, 域名={domain}, 需要代理={need_proxy}, source_id={source_id}, proxy_group={proxy_group}")
        
        # 尝试获取代理管理器
        try:
            from worker.utils.proxy_manager import proxy_manager
            proxy_manager_loaded = True
        except ImportError:
            try:
                from backend.worker.utils.proxy_manager import proxy_manager
                proxy_manager_loaded = True
            except ImportError:
                proxy_manager = None
                proxy_manager_loaded = False
                logger.warning("无法导入代理管理器，将不使用代理或仅使用指定的代理")
        
        while retry_count <= max_retries:
            start_time = None
            proxy_used = False
            
            try:
                # 获取会话
                session = await self._get_session()
                
                # 如果需要代理且代理管理器可用，尝试获取代理
                if need_proxy and proxy_manager_loaded and not proxy_url:
                    try:
                        proxy_config = await proxy_manager.get_proxy(source_id, proxy_group)
                        if proxy_config:
                            proxy_url = proxy_config.get("url")
                            logger.info(f"从代理管理器获取代理: {proxy_url} 用于请求 {url}")
                        else:
                            logger.warning(f"代理管理器未返回可用代理，使用 source_id={source_id}, proxy_group={proxy_group}")
                    except Exception as e:
                        logger.warning(f"从代理管理器获取代理失败: {str(e)}")
                
                # 设置代理参数
                request_kwargs = dict(kwargs)
                if proxy_url:
                    request_kwargs["proxy"] = proxy_url
                    proxy_used = True
                    logger.info(f"使用代理 {proxy_url} 请求 {url}")
                    start_time = asyncio.get_event_loop().time()
                else:
                    logger.info(f"未使用代理直接请求 {url}")
                
                # 发送请求
                try:
                    async with session.request(method, url, **request_kwargs) as response:
                        status = response.status
                        
                        # 计算请求耗时
                        if start_time is not None:
                            elapsed = asyncio.get_event_loop().time() - start_time
                        else:
                            elapsed = None
                        
                        # 向代理管理器报告代理状态
                        if proxy_used and proxy_manager_loaded and proxy_config and proxy_config.get('id'):
                            success = 200 <= status < 300
                            try:
                                await proxy_manager.report_proxy_status(proxy_config.get('id'), success, elapsed)
                                if success:
                                    logger.info(f"通过代理成功请求 {url}, 状态码: {status}, 耗时: {elapsed:.2f}s")
                                else:
                                    logger.warning(f"通过代理请求 {url} 返回状态码: {status}")
                            except Exception as e:
                                logger.warning(f"报告代理状态时出错: {str(e)}")
                        
                        # 根据响应类型处理
                        if response_type == 'json':
                            try:
                                data = await response.json()
                            except (json.JSONDecodeError, aiohttp.ContentTypeError):
                                # 如果JSON解析失败，尝试读取文本
                                text = await response.text()
                                data = {'text': text, 'error': 'JSON解析失败'}
                        elif response_type == 'text':
                            data = await response.text()
                        elif response_type == 'binary':
                            data = await response.read()
                        else:
                            data = await response.json()
                        
                        return {
                            'status': status,
                            'data': data,
                            'headers': dict(response.headers),
                            'url': str(response.url)
                        }
                
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    # 代理请求失败时报告状态
                    if proxy_used and proxy_manager_loaded and proxy_config and proxy_config.get('id'):
                        try:
                            await proxy_manager.report_proxy_status(proxy_config.get('id'), False)
                            logger.warning(f"通过代理请求 {url} 失败: {str(e)}")
                        except Exception as e2:
                            logger.warning(f"报告代理失败状态时出错: {str(e2)}")
                    
                    # 如果允许回退且有其他重试机会，重试但不使用代理
                    if proxy_used and proxy_fallback and retry_count < max_retries:
                        logger.info(f"代理请求失败，将尝试直连请求: {url}")
                        proxy_url = None
                        retry_count += 1
                        await asyncio.sleep(retry_delay)
                        continue
                    
                    # 否则抛出异常进行标准重试流程
                    raise
            
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as e:
                error_msg = str(e)
                retry_count += 1
                
                # 特殊处理事件循环错误和会话连接器错误
                if ("Event loop is closed" in error_msg or 
                    "different loop" in error_msg or
                    "Session and connector" in error_msg):
                    logger.warning(f"HTTP请求出现事件循环错误: {error_msg}")
                    # 删除当前会话，强制在下次请求中创建新会话
                    current_thread_id = threading.get_ident()
                    if hasattr(_thread_local, 'sessions') and current_thread_id in _thread_local.sessions:
                        try:
                            if not _thread_local.sessions[current_thread_id].closed:
                                await _thread_local.sessions[current_thread_id].close()
                        except Exception:
                            pass
                        _thread_local.sessions.pop(current_thread_id, None)
                    
                    # 需要重新创建事件循环
                    if current_thread_id in _thread_eventloops:
                        _thread_eventloops.pop(current_thread_id, None)
                
                # 如果还有重试机会，等待后重试
                if retry_count <= max_retries:
                    logger.warning(f"HTTP请求失败 ({retry_count}/{max_retries}): {url}, 错误: {error_msg}, {retry_delay}秒后重试")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"HTTP请求最终失败: {url}, 错误: {error_msg}")
                    return {
                        'status': -1,
                        'data': {'error': f"请求失败: {error_msg}"},
                        'headers': {},
                        'url': url
                    }
            
            except Exception as e:
                logger.error(f"HTTP请求未预期错误: {url}, 错误: {str(e)}")
                return {
                    'status': -2,
                    'data': {'error': f"未预期错误: {str(e)}"},
                    'headers': {},
                    'url': url
                }
    
    # 便捷方法
    async def get(self, url: str, **kwargs) -> Dict[str, Any]:
        """发送GET请求"""
        return await self.request('GET', url, **kwargs)
    
    async def post(self, url: str, **kwargs) -> Dict[str, Any]:
        """发送POST请求"""
        return await self.request('POST', url, **kwargs)
    
    # 缓存请求方法
    @cached(ttl=300, cache=Cache.MEMORY, key_builder=lambda *args, **kwargs: f"http_get:{args[1]}", serializer=JsonSerializer())
    async def cached_get(self, url: str, **kwargs) -> Dict[str, Any]:
        """带缓存的GET请求"""
        return await self.get(url, **kwargs)
    
    # 添加fetch方法
    async def fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Dict[str, str] = None,
        params: Dict[str, Any] = None,
        json_data: Dict[str, Any] = None,
        response_type: str = "json",
        **kwargs
    ) -> Any:
        """
        统一的数据获取方法，返回处理后的响应内容
        这是APINewsSource等类使用的主要方法
        支持代理管理器配置
        """
        max_retries = kwargs.pop('max_retries', 3)
        retry_delay = kwargs.pop('retry_delay', 2)
        retry_count = 0
        last_error = None
        thread_id = threading.get_ident()
        
        # 提取代理相关参数，但不从kwargs中移除，让request方法处理
        source_id = kwargs.get('source_id')
        need_proxy = kwargs.get('need_proxy', False)
        proxy_group = kwargs.get('proxy_group', 'default')
        proxy_fallback = kwargs.get('proxy_fallback', True)
        
        # 检查域名是否需要代理
        if not need_proxy and url:
            try:
                import urllib.parse
                domain = urllib.parse.urlparse(url).netloc
                # 尝试从配置中获取代理域名列表
                proxy_required_domains = []
                try:
                    from app.core.config import settings
                    proxy_required_domains = settings.proxy_domains
                except ImportError:
                    # 如果无法导入设置，使用默认列表
                    proxy_required_domains = [
                        "github.com", "bloomberg.com", "hackernews.firebaseio.com", 
                        "news.ycombinator.com", "bbc.com", "v2ex.com", "producthunt.com",
                        "xueqiu.com", "stock.xueqiu.com", "news.google.com", "google.com",
                        "bbc.co.uk", "fastbull.cn", "ft.com",
                        "nytimes.com", "wsj.com", "forbes.com", "cnbc.com",
                        "reuters.com", "cnbc.com", "economist.com", "feeds.bbci.co.uk", "bbci.co.uk"
                    ]
                
                if domain and any(required_domain in domain for required_domain in proxy_required_domains):
                    need_proxy = True
                    kwargs['need_proxy'] = True
                    logger.info(f"全局fetch: 域名 {domain} 在需要代理的列表中，自动启用代理")
                else:
                    logger.debug(f"全局fetch: 域名 {domain} 不在代理列表中，使用直连")
            except Exception as e:
                logger.warning(f"解析URL域名时出错: {str(e)}")
        
        while retry_count <= max_retries:
            try:
                # 每次重试前重置事件循环状态
                if retry_count > 0:
                    logger.info(f"第 {retry_count} 次重试获取数据: {url}")
                    
                    # 强制清理旧会话
                    if hasattr(_thread_local, 'sessions') and thread_id in _thread_local.sessions:
                        try:
                            old_session = _thread_local.sessions[thread_id]
                            if old_session and not old_session.closed:
                                try:
                                    await old_session.close()
                                except RuntimeError as e:
                                    if "Event loop is closed" not in str(e):
                                        logger.warning(f"关闭旧会话出错: {str(e)}")
                        except Exception as e:
                            logger.warning(f"访问或关闭旧会话时出错: {str(e)}")
                        
                        # 移除旧会话
                        _thread_local.sessions.pop(thread_id, None)
                    
                    # 如果有事件循环问题，尝试创建新的事件循环
                    if isinstance(last_error, RuntimeError) and "Event loop is closed" in str(last_error):
                        try:
                            # 清理旧事件循环记录
                            if thread_id in _thread_eventloops:
                                _thread_eventloops.pop(thread_id, None)
                            
                            # 创建新事件循环
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            _thread_eventloops[thread_id] = loop
                            logger.info(f"为线程 {thread_id} 创建了新的事件循环用于第{retry_count}次重试")
                        except Exception as e:
                            logger.error(f"创建新事件循环失败: {str(e)}")
                
                # 构建请求参数
                request_kwargs = {}
                
                # 添加头信息
                if headers:
                    request_kwargs["headers"] = headers
                    
                # 添加查询参数
                if params:
                    request_kwargs["params"] = params
                    
                # 添加JSON数据
                if json_data:
                    request_kwargs["json"] = json_data
                    
                # 添加代理相关参数
                request_kwargs["source_id"] = source_id
                request_kwargs["need_proxy"] = need_proxy
                request_kwargs["proxy_group"] = proxy_group
                request_kwargs["proxy_fallback"] = proxy_fallback
                
                # 添加其他关键字参数
                request_kwargs.update(kwargs)
                
                # 添加响应类型
                request_kwargs["response_type"] = response_type
                
                # 发送请求
                try:
                    response = await self.request(method, url, **request_kwargs)
                except RuntimeError as e:
                    if "Event loop is closed" in str(e):
                        retry_count += 1
                        last_error = e
                        logger.warning(f"fetch请求失败 (事件循环已关闭): {url}, 将进行第 {retry_count} 次重试")
                        # 创建新的事件循环
                        try:
                            if thread_id in _thread_eventloops:
                                _thread_eventloops.pop(thread_id, None)
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            _thread_eventloops[thread_id] = loop
                            logger.info(f"在请求中为线程 {thread_id} 创建了新的事件循环")
                        except Exception as e2:
                            logger.error(f"创建新事件循环失败: {str(e2)}")
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        raise
                
                # 检查状态码
                if response["status"] < 200 or response["status"] >= 300:
                    logger.warning(f"Fetch请求返回非成功状态码: {response['status']}, URL: {url}")
                    # 对于特定错误码进行重试
                    if response["status"] in [429, 500, 502, 503, 504] and retry_count < max_retries:
                        retry_count += 1
                        last_error = Exception(f"HTTP状态码: {response['status']}")
                        logger.warning(f"状态码{response['status']}，将在{retry_delay}秒后进行第{retry_count}次重试")
                        await asyncio.sleep(retry_delay)
                        continue
                    
                # 根据响应类型返回适当的结果
                return response["data"]
                    
            except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as e:
                retry_count += 1
                last_error = e
                error_msg = str(e)
                
                if retry_count <= max_retries:
                    logger.warning(f"Fetch请求失败 ({retry_count}/{max_retries}): {url}, 错误: {error_msg}")
                    # 指数退避重试
                    await asyncio.sleep(retry_delay * (2 ** (retry_count - 1)))
                else:
                    logger.error(f"Fetch请求最终失败: {url}, 错误: {error_msg}")
                    # 如果是响应类型为json，返回错误JSON
                    if response_type == "json":
                        return {"error": f"请求失败: {error_msg}"}
                    elif response_type == "text":
                        return f"Error: {error_msg}"
                    else:
                        return None
            
            except json.JSONDecodeError as e:
                # JSON解析错误，可能是响应格式错误
                logger.error(f"JSON解析错误: {url}, 错误: {str(e)}")
                if response_type == "json":
                    return {"error": f"JSON解析错误: {str(e)}"}
                elif response_type == "text":
                    return f"Error: JSON解析错误: {str(e)}"
                else:
                    return None
                
            except Exception as e:
                retry_count += 1
                last_error = e
                logger.error(f"Fetch请求未预期错误: {url}, 错误: {str(e)}")
                
                # 特别处理事件循环错误
                if isinstance(e, RuntimeError) and "Event loop is closed" in str(e) and retry_count <= max_retries:
                    logger.warning(f"检测到事件循环已关闭，将尝试第 {retry_count} 次重试")
                    await asyncio.sleep(retry_delay)
                    continue
                
                # 返回适当的错误结果
                if response_type == "json":
                    return {"error": f"未预期错误: {str(e)}"}
                elif response_type == "text":
                    return f"Error: {str(e)}"
                else:
                    return None
                
        # 所有重试都失败
        logger.error(f"Fetch请求经过{max_retries}次重试后仍然失败: {url}")
        if response_type == "json":
            return {"error": f"多次重试后仍然失败: {str(last_error)}"}
        elif response_type == "text":
            return f"Error: 多次重试后仍然失败: {str(last_error)}"
        else:
            return None

# 创建默认客户端实例
default_client = HTTPClient()

# 设置http_client为default_client的别名，确保向后兼容性
http_client = default_client

# 工具函数
async def get(url: str, **kwargs) -> Dict[str, Any]:
    """使用默认客户端发送GET请求"""
    return await default_client.get(url, **kwargs)

async def post(url: str, **kwargs) -> Dict[str, Any]:
    """使用默认客户端发送POST请求"""
    return await default_client.post(url, **kwargs)

async def cached_get(url: str, **kwargs) -> Dict[str, Any]:
    """使用默认客户端发送带缓存的GET请求"""
    return await default_client.cached_get(url, **kwargs)

async def fetch(url: str, **kwargs) -> Any:
    """
    使用默认客户端获取数据
    支持代理配置，自动检测需要代理的域名
    """
    retry_count = 0
    max_retries = kwargs.pop('max_retries', 3) 
    retry_delay = kwargs.pop('retry_delay', 2)
    thread_id = threading.get_ident()
    
    # 检查域名是否需要代理
    need_proxy = kwargs.get('need_proxy', False)
    if not need_proxy and url:
        try:
            import urllib.parse
            domain = urllib.parse.urlparse(url).netloc
            # 尝试从配置中获取代理域名列表
            proxy_required_domains = []
            try:
                from app.core.config import settings
                proxy_required_domains = settings.proxy_domains
            except ImportError:
                # 如果无法导入设置，使用默认列表
                proxy_required_domains = [
                    "github.com", "bloomberg.com", "hackernews.firebaseio.com", 
                    "news.ycombinator.com", "bbc.com", "v2ex.com", "producthunt.com",
                    "xueqiu.com", "stock.xueqiu.com", "news.google.com", "google.com",
                    "bbc.co.uk", "fastbull.cn", "ft.com",
                    "nytimes.com", "wsj.com", "forbes.com", "cnbc.com",
                    "reuters.com", "cnbc.com", "economist.com", "feeds.bbci.co.uk", "bbci.co.uk"
                ]
            
            if domain and any(required_domain in domain for required_domain in proxy_required_domains):
                need_proxy = True
                kwargs['need_proxy'] = True
                logger.info(f"全局fetch: 域名 {domain} 在需要代理的列表中，自动启用代理")
            else:
                logger.debug(f"全局fetch: 域名 {domain} 不在代理列表中，使用直连")
        except Exception as e:
            logger.warning(f"解析URL域名时出错: {str(e)}")
    
    # 强制使用代理进行调试
    if not need_proxy and kwargs.get('debug_proxy', False):
        need_proxy = True
        kwargs['need_proxy'] = True
        logger.info(f"全局fetch: 强制使用代理模式（debug_proxy=True）")
    
    # 尝试获取代理管理器，确保它可用
    try:
        from worker.utils.proxy_manager import proxy_manager
        # 尝试刷新代理列表
        await proxy_manager.refresh_proxies()
        logger.debug(f"全局fetch: 代理管理器可用，代理列表已刷新")
    except Exception as e:
        logger.warning(f"全局fetch: 加载或刷新代理管理器失败: {str(e)}")
    
    while retry_count <= max_retries:
        try:
            # 每次尝试都重置事件循环状态
            if retry_count > 0:
                logger.debug(f"第 {retry_count} 次重试获取数据: {url}")
                
                # 清理旧会话
                if hasattr(_thread_local, 'sessions') and thread_id in _thread_local.sessions:
                    try:
                        old_session = _thread_local.sessions[thread_id]
                        if old_session and not old_session.closed:
                            await old_session.close()
                    except Exception as e:
                        if "Event loop is closed" not in str(e):
                            logger.warning(f"关闭旧会话出错: {str(e)}")
                    # 移除旧会话
                    _thread_local.sessions.pop(thread_id, None)
                
                # 重置事件循环
                if thread_id in _thread_eventloops:
                    _thread_eventloops.pop(thread_id, None)
                
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    _thread_eventloops[thread_id] = loop
                    logger.debug(f"为线程 {thread_id} 创建了新的事件循环用于第{retry_count}次重试")
                except Exception as e:
                    logger.error(f"创建新事件循环失败: {str(e)}")
            
            # 确保代理参数传递
            kwargs['need_proxy'] = need_proxy
            
            # 调用客户端fetch
            logger.debug(f"发起请求 {url}，need_proxy={need_proxy}")
            result = await default_client.fetch(url, **kwargs)
            return result
            
        except Exception as e:
            retry_count += 1
            error_msg = str(e)
            
            # 记录错误
            if retry_count <= max_retries:
                logger.warning(f"fetch操作失败 ({retry_count}/{max_retries}): {error_msg}")
                
                # 对事件循环相关错误进行特殊处理
                if ("Event loop is closed" in error_msg or 
                    "different loop" in error_msg or 
                    "Session and connector" in error_msg):
                    
                    # 强制清理会话和事件循环状态
                    if hasattr(_thread_local, 'sessions'):
                        for session_id, session in list(_thread_local.sessions.items()):
                            try:
                                if session and not session.closed:
                                    await session.close()
                            except Exception:
                                pass
                        _thread_local.sessions.clear()
                    
                    # 清理所有事件循环记录
                    _thread_eventloops.clear()
                    
                    # 创建全新的事件循环
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        _thread_eventloops[thread_id] = loop
                        logger.info(f"为线程 {thread_id} 完全重置并创建了新的事件循环")
                    except Exception as e2:
                        logger.error(f"重置事件循环失败: {str(e2)}")
                
                # 使用指数退避策略
                wait_time = retry_delay * (2 ** (retry_count - 1))
                logger.info(f"等待 {wait_time:.1f} 秒后进行第 {retry_count} 次重试...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"所有重试都失败 ({retry_count-1}/{max_retries}): {error_msg}")
                if "json" in kwargs.get("response_type", "json").lower():
                    return {"error": f"请求失败: {error_msg}", "url": url}
                else:
                    return f"Error: {error_msg}"
    
    # 不应该到达这里，但为了安全起见
    logger.error(f"fetch操作异常情况: 超过最大重试次数 {max_retries}")
    return {"error": "超过最大重试次数", "url": url}

# 进程退出前清理资源
import atexit
import asyncio

def cleanup():
    """在进程退出时清理资源"""
    try:
        # 从线程映射中获取事件循环
        for thread_id, loop in _thread_eventloops.items():
            if loop and not loop.is_closed():
                # 获取所有线程会话并关闭
                if hasattr(_thread_local, 'sessions'):
                    for session_thread_id, session in list(_thread_local.sessions.items()):
                        if session and not session.closed and session_thread_id == thread_id:
                            try:
                                loop.run_until_complete(session.close())
                                logger.debug(f"已清理线程 {session_thread_id} 的HTTP会话")
                            except Exception:
                                pass
        
        # 清理默认事件循环
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                # 关闭默认客户端会话
                if default_client.session and not default_client.session.closed:
                    try:
                        loop.run_until_complete(default_client.close())
                        logger.debug("已清理默认HTTP客户端")
                    except Exception:
                        pass
        except Exception:
            pass
                
        # 清理会话表
        if hasattr(_thread_local, 'sessions'):
            _thread_local.sessions.clear()
            
    except Exception as e:
        logger.warning(f"清理HTTP资源时出错: {str(e)}")

# 注册清理函数
atexit.register(cleanup)

# 记录修复已应用
logger.info("✅ HTTP客户端连接器和会话事件循环修复已应用：已增强事件循环管理和多线程支持") 