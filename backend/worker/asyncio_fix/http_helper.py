"""
安全的HTTP请求助手模块

提供更可靠的HTTP请求函数，内建错误处理和重试机制，
特别处理事件循环相关的错误。
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Union, List, Tuple
import functools
import random

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 尝试导入aiohttp
try:
    import aiohttp
    HAVE_AIOHTTP = True
except ImportError:
    HAVE_AIOHTTP = False
    logger.warning("未安装aiohttp库，HTTP请求功能将不可用")

# 导入事件循环修复模块
try:
    from backend.worker.asyncio_fix.auto_fix import get_or_create_eventloop, run_async, ensure_event_loop
except ImportError:
    try:
        from worker.asyncio_fix.auto_fix import get_or_create_eventloop, run_async, ensure_event_loop
    except ImportError:
        logger.error("无法导入事件循环修复模块，HTTP请求可能不稳定")
        # 提供简单的后备实现
        def get_or_create_eventloop():
            try:
                return asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return loop
        
        def run_async(coro):
            loop = get_or_create_eventloop()
            return loop.run_until_complete(coro)
        
        def ensure_event_loop(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
            return wrapper

# 安全的HTTP请求函数
@ensure_event_loop
async def safe_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    data: Any = None,
    json: Any = None,
    cookies: Optional[Dict[str, str]] = None,
    timeout: float = 30.0,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    return_json: bool = False,
    verify_ssl: bool = True,
    user_agent: Optional[str] = None,
    proxy: Optional[str] = None,
    verbose: bool = False
) -> Tuple[bool, Any, Optional[str]]:
    """
    执行一个安全的HTTP请求，自动处理各种错误情况
    
    Args:
        url: 请求的URL
        method: HTTP方法 (GET, POST, PUT, DELETE 等)
        headers: HTTP头
        params: URL查询参数
        data: 表单数据或二进制数据
        json: JSON数据 (会自动设置Content-Type为application/json)
        cookies: Cookies
        timeout: 请求超时时间(秒)
        max_retries: 最大重试次数
        retry_delay: 重试延迟(秒)
        return_json: 是否将响应解析为JSON
        verify_ssl: 是否验证SSL证书
        user_agent: 自定义User-Agent
        proxy: 使用的代理服务器URL
        verbose: 是否打印详细日志
        
    Returns:
        (success, result, error_message)
        - success: 请求是否成功
        - result: 成功时为响应内容，失败时为None
        - error_message: 失败时的错误信息，成功时为None
    """
    if not HAVE_AIOHTTP:
        return False, None, "未安装aiohttp库"
        
    # 准备headers
    if headers is None:
        headers = {}
    
    # 添加默认User-Agent，如果未指定
    if 'User-Agent' not in headers and user_agent:
        headers['User-Agent'] = user_agent
    elif 'User-Agent' not in headers:
        headers['User-Agent'] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36"
    
    # 准备代理
    if proxy:
        proxy_settings = {
            'http': proxy,
            'https': proxy
        }
    else:
        proxy_settings = None
    
    # 设置超时
    timeout_obj = aiohttp.ClientTimeout(total=timeout)
    
    retry_count = 0
    last_error = None
    
    while retry_count <= max_retries:
        if retry_count > 0:
            # 计算退避延迟 (指数退避 + 随机抖动)
            delay = retry_delay * (2 ** (retry_count - 1)) * (0.5 + random.random())
            if verbose:
                logger.info(f"重试请求 {url}，等待 {delay:.2f} 秒...")
            await asyncio.sleep(delay)
        
        retry_count += 1
        
        try:
            # 确保事件循环有效
            loop = get_or_create_eventloop()
            
            # 创建会话并发送请求
            async with aiohttp.ClientSession(timeout=timeout_obj, trust_env=True) as session:
                async with session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    data=data,
                    json=json,
                    cookies=cookies,
                    ssl=verify_ssl,
                    proxy=proxy
                ) as response:
                    # 检查响应状态
                    if response.status >= 400:
                        error_text = await response.text()
                        error_msg = f"HTTP错误 {response.status}: {error_text[:500]}..."
                        if verbose:
                            logger.error(error_msg)
                        last_error = error_msg
                        
                        # 检查是否应该重试
                        if response.status in [429, 500, 502, 503, 504] and retry_count <= max_retries:
                            continue
                        else:
                            return False, None, error_msg
                    
                    # 获取响应内容
                    if return_json:
                        try:
                            result = await response.json()
                        except Exception as e:
                            # JSON解析失败，尝试获取文本
                            content = await response.text()
                            error_msg = f"JSON解析错误: {str(e)}, 响应内容: {content[:500]}..."
                            if verbose:
                                logger.error(error_msg)
                            return False, content, error_msg
                    else:
                        result = await response.text()
                    
                    # 请求成功
                    return True, result, None
                    
        except asyncio.TimeoutError:
            last_error = f"请求超时 (>{timeout}秒)"
            if verbose:
                logger.warning(f"{last_error}, 重试 {retry_count}/{max_retries}")
        except aiohttp.ClientError as e:
            last_error = f"HTTP客户端错误: {str(e)}"
            if verbose:
                logger.warning(f"{last_error}, 重试 {retry_count}/{max_retries}")
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                last_error = "事件循环已关闭，尝试创建新循环"
                if verbose:
                    logger.warning(f"{last_error}, 重试 {retry_count}/{max_retries}")
                # 创建新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            else:
                last_error = f"运行时错误: {str(e)}"
                if verbose:
                    logger.error(last_error)
                # 非事件循环错误不重试
                break
        except Exception as e:
            last_error = f"未预期的错误: {str(e)}"
            if verbose:
                logger.error(f"{last_error}, 重试 {retry_count}/{max_retries}")
    
    # 所有重试都失败了
    return False, None, f"请求失败，已重试 {max_retries} 次: {last_error}"


def fetch_url(url: str, **kwargs) -> Tuple[bool, Any, Optional[str]]:
    """
    同步版本的URL请求函数，内部使用safe_request
    
    Args:
        url: 请求的URL
        **kwargs: 传递给safe_request的其他参数
        
    Returns:
        与safe_request相同的返回值
    """
    return run_async(safe_request(url, **kwargs))


async def batch_fetch_urls(
    urls: List[str],
    concurrency: int = 5,
    **kwargs
) -> List[Tuple[str, bool, Any, Optional[str]]]:
    """
    批量获取多个URL的内容
    
    Args:
        urls: URL列表
        concurrency: 并发请求数量
        **kwargs: 传递给safe_request的其他参数
        
    Returns:
        结果列表，每项是(url, success, result, error_message)
    """
    # 限制并发请求的信号量
    semaphore = asyncio.Semaphore(concurrency)
    
    async def fetch_with_semaphore(url):
        async with semaphore:
            success, result, error = await safe_request(url, **kwargs)
            return url, success, result, error
    
    # 创建所有请求任务
    tasks = [fetch_with_semaphore(url) for url in urls]
    
    # 使用gather安全地并行执行
    try:
        return await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logger.error(f"批量请求执行错误: {str(e)}")
        return [(url, False, None, str(e)) for url in urls] 