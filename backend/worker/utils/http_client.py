import json
from typing import Any, Dict, Optional, Union

import aiohttp
from aiohttp import ClientSession, ClientTimeout
from aiocache import cached, Cache
from aiocache.serializers import JsonSerializer

from app.core.config import settings


class HTTPClient:
    """
    Async HTTP client with caching support
    """
    
    def __init__(self, timeout: int = 30):
        self.timeout = ClientTimeout(total=timeout)
        self.session = None
    
    async def _get_session(self) -> ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self.session
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    def __del__(self):
        """
        确保在对象被垃圾回收时关闭会话
        """
        if self.session and not self.session.closed:
            import sys
            # 检查Python是否正在关闭
            if sys.meta_path is None:
                return  # Python正在关闭，不要尝试关闭会话
                
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.close())
                else:
                    loop.run_until_complete(self.close())
            except Exception:
                # 如果无法获取事件循环或事件循环已关闭，则忽略
                pass
    
    @cached(
        ttl=settings.DEFAULT_CACHE_TTL,
        cache=Cache.REDIS,
        key_builder=lambda *args, **kwargs: f"http_cache:{kwargs.get('url')}:{json.dumps(kwargs.get('params', {}))}",
        serializer=JsonSerializer(),
        namespace="http_client"
    )
    async def fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        response_type: str = "json",
        cache: bool = True,
        timeout: Optional[int] = None
    ) -> Any:
        """
        Fetch data from URL with caching support
        
        Args:
            url: URL to fetch
            method: HTTP method (GET, POST, etc.)
            headers: HTTP headers
            params: Query parameters
            data: Form data
            json_data: JSON data
            response_type: Response type (json, text, bytes)
            cache: Whether to use cache
            timeout: Request timeout in seconds
            
        Returns:
            Response data based on response_type
        """
        session = await self._get_session()
        
        if timeout:
            timeout_obj = ClientTimeout(total=timeout)
        else:
            timeout_obj = self.timeout
        
        async with session.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            data=data,
            json=json_data,
            timeout=timeout_obj
        ) as response:
            response.raise_for_status()
            
            if response_type == "json":
                return await response.json()
            elif response_type == "text":
                return await response.text()
            elif response_type == "bytes":
                return await response.read()
            else:
                raise ValueError(f"Unsupported response type: {response_type}")


# Singleton instance
http_client = HTTPClient() 