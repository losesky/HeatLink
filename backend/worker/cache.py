import logging
import json
import pickle
import time
from typing import Dict, Any, Optional, List, Union

import aioredis

logger = logging.getLogger(__name__)


class CacheManager:
    """
    缓存管理器
    支持内存缓存和Redis缓存
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        enable_memory_cache: bool = True,
        default_ttl: int = 900  # 默认缓存时间，单位秒，默认15分钟
    ):
        self.redis_url = redis_url
        self.enable_memory_cache = enable_memory_cache
        self.default_ttl = default_ttl
        
        # 内存缓存
        self.memory_cache: Dict[str, Dict[str, Any]] = {}
        
        # Redis连接
        self.redis = None
        
        # 初始化标志
        self.initialized = False
    
    async def initialize(self):
        """
        初始化缓存管理器
        """
        if self.initialized:
            return
        
        # 如果启用Redis缓存，则创建Redis连接
        if self.redis_url:
            try:
                self.redis = await aioredis.create_redis_pool(self.redis_url)
                logger.info(f"Connected to Redis: {self.redis_url}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {str(e)}")
                self.redis = None
        
        # 初始化完成
        self.initialized = True
        logger.info(f"Cache manager initialized, memory cache: {self.enable_memory_cache}, Redis: {self.redis is not None}")
    
    async def close(self):
        """
        关闭缓存管理器
        """
        # 如果有Redis连接，则关闭
        if self.redis:
            self.redis.close()
            await self.redis.wait_closed()
            self.redis = None
            logger.info("Redis connection closed")
        
        # 清空内存缓存
        self.memory_cache.clear()
        
        # 重置初始化标志
        self.initialized = False
        
        logger.info("Cache manager closed")
    
    async def get(self, key: str) -> Optional[Any]:
        """
        获取缓存数据
        """
        # 确保初始化完成
        if not self.initialized:
            await self.initialize()
        
        # 尝试从内存缓存获取
        if self.enable_memory_cache:
            cache_item = self.memory_cache.get(key)
            if cache_item:
                # 检查是否过期
                if cache_item.get("expire_time", 0) > time.time():
                    logger.debug(f"Memory cache hit: {key}")
                    return cache_item.get("data")
                else:
                    # 过期，删除缓存
                    del self.memory_cache[key]
        
        # 如果有Redis连接，则尝试从Redis获取
        if self.redis:
            try:
                # 获取数据
                data = await self.redis.get(key)
                if data:
                    # 反序列化
                    try:
                        result = pickle.loads(data)
                        
                        # 如果启用内存缓存，则存入内存缓存
                        if self.enable_memory_cache:
                            # 获取TTL
                            ttl = await self.redis.ttl(key)
                            if ttl > 0:
                                expire_time = time.time() + ttl
                                self.memory_cache[key] = {
                                    "data": result,
                                    "expire_time": expire_time
                                }
                        
                        logger.debug(f"Redis cache hit: {key}")
                        return result
                    except Exception as e:
                        logger.error(f"Failed to deserialize Redis data: {str(e)}")
            except Exception as e:
                logger.error(f"Failed to get data from Redis: {str(e)}")
        
        # 缓存未命中
        logger.debug(f"Cache miss: {key}")
        return None
    
    async def set(self, key: str, data: Any, ttl: Optional[int] = None):
        """
        设置缓存数据
        """
        # 确保初始化完成
        if not self.initialized:
            await self.initialize()
        
        # 使用默认TTL
        if ttl is None:
            ttl = self.default_ttl
        
        # 如果启用内存缓存，则存入内存缓存
        if self.enable_memory_cache:
            expire_time = time.time() + ttl
            self.memory_cache[key] = {
                "data": data,
                "expire_time": expire_time
            }
        
        # 如果有Redis连接，则存入Redis
        if self.redis:
            try:
                # 序列化
                serialized_data = pickle.dumps(data)
                
                # 存入Redis
                await self.redis.setex(key, ttl, serialized_data)
                
                logger.debug(f"Set Redis cache: {key}, ttl: {ttl}s")
            except Exception as e:
                logger.error(f"Failed to set data to Redis: {str(e)}")
    
    async def delete(self, key: str):
        """
        删除缓存数据
        """
        # 确保初始化完成
        if not self.initialized:
            await self.initialize()
        
        # 如果启用内存缓存，则删除内存缓存
        if self.enable_memory_cache and key in self.memory_cache:
            del self.memory_cache[key]
        
        # 如果有Redis连接，则删除Redis缓存
        if self.redis:
            try:
                await self.redis.delete(key)
                logger.debug(f"Deleted Redis cache: {key}")
            except Exception as e:
                logger.error(f"Failed to delete data from Redis: {str(e)}")
    
    async def clear(self, pattern: str = "*"):
        """
        清空缓存
        """
        # 确保初始化完成
        if not self.initialized:
            await self.initialize()
        
        # 如果启用内存缓存，则清空内存缓存
        if self.enable_memory_cache:
            if pattern == "*":
                self.memory_cache.clear()
            else:
                # 删除匹配的键
                keys_to_delete = [k for k in self.memory_cache.keys() if k.startswith(pattern.replace("*", ""))]
                for key in keys_to_delete:
                    del self.memory_cache[key]
        
        # 如果有Redis连接，则清空Redis缓存
        if self.redis:
            try:
                # 获取匹配的键
                keys = await self.redis.keys(pattern)
                if keys:
                    # 删除键
                    await self.redis.delete(*keys)
                    logger.info(f"Cleared Redis cache, pattern: {pattern}, count: {len(keys)}")
            except Exception as e:
                logger.error(f"Failed to clear Redis cache: {str(e)}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        """
        # 确保初始化完成
        if not self.initialized:
            await self.initialize()
        
        stats = {
            "memory_cache_enabled": self.enable_memory_cache,
            "redis_enabled": self.redis is not None,
            "memory_cache_count": len(self.memory_cache) if self.enable_memory_cache else 0,
            "redis_count": 0
        }
        
        # 如果有Redis连接，则获取Redis统计信息
        if self.redis:
            try:
                # 获取所有键
                keys = await self.redis.keys("*")
                stats["redis_count"] = len(keys)
                
                # 获取Redis信息
                info = await self.redis.info()
                stats["redis_info"] = {
                    "used_memory": info.get("used_memory_human", ""),
                    "used_memory_peak": info.get("used_memory_peak_human", ""),
                    "total_connections_received": info.get("total_connections_received", 0),
                    "total_commands_processed": info.get("total_commands_processed", 0)
                }
            except Exception as e:
                logger.error(f"Failed to get Redis stats: {str(e)}")
        
        return stats 