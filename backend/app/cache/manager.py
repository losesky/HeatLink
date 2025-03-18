#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
缓存管理器模块

提供统一的缓存管理接口，支持Redis和内存缓存。
"""

import json
import logging
import asyncio
from typing import Any, Dict, List, Optional, Union

import aioredis
from aiocache import Cache, caches
from aiocache.backends.redis import RedisCache
from aiocache.backends.memory import MemoryCache

logger = logging.getLogger(__name__)

class CacheManager:
    """缓存管理器，提供统一的缓存管理接口"""
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        enable_memory_cache: bool = True,
        default_ttl: int = 300,
        namespace: str = "heatlink"
    ):
        """
        初始化缓存管理器
        
        Args:
            redis_url: Redis连接URL
            enable_memory_cache: 是否启用内存缓存
            default_ttl: 默认缓存过期时间（秒）
            namespace: 缓存命名空间
        """
        self.redis_url = redis_url
        self.enable_memory_cache = enable_memory_cache
        self.default_ttl = default_ttl
        self.namespace = namespace
        self.redis_client = None
        self.memory_cache = None
        self.initialized = False
    
    async def initialize(self):
        """初始化缓存连接"""
        try:
            # 初始化Redis缓存
            self.redis_client = await aioredis.create_redis_pool(self.redis_url)
            logger.info(f"Connected to Redis: {self.redis_url}")
            
            # 初始化内存缓存
            if self.enable_memory_cache:
                self.memory_cache = MemoryCache(namespace=self.namespace)
                await self.memory_cache.clear()
            
            self.initialized = True
            logger.info(f"Cache manager initialized, memory cache: {self.enable_memory_cache}, Redis: {self.redis_client is not None}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize cache manager: {str(e)}")
            return False
    
    async def close(self):
        """关闭缓存连接"""
        try:
            if self.redis_client:
                self.redis_client.close()
                await self.redis_client.wait_closed()
                logger.info("Redis connection closed")
            
            if self.memory_cache:
                await self.memory_cache.clear()
                logger.info("Memory cache cleared")
                
            self.initialized = False
        except Exception as e:
            logger.error(f"Error closing cache connections: {str(e)}")
    
    async def get(self, key: str) -> Any:
        """
        获取缓存值
        
        Args:
            key: 缓存键
        
        Returns:
            缓存的值，如果不存在则返回None
        """
        if not self.initialized:
            logger.warning("Cache manager not initialized, skipping get operation")
            return None
        
        try:
            # 首先尝试从内存缓存获取
            if self.memory_cache:
                value = await self.memory_cache.get(key)
                if value is not None:
                    logger.debug(f"Cache hit (memory): {key}")
                    return value
            
            # 然后尝试从Redis获取
            if self.redis_client:
                value = await self.redis_client.get(key)
                if value is not None:
                    # 将字节转换为Python对象
                    value_str = value.decode('utf-8')
                    try:
                        value_obj = json.loads(value_str)
                        logger.debug(f"Cache hit (redis): {key}")
                        
                        # 如果启用了内存缓存，也存入内存缓存
                        if self.memory_cache:
                            await self.memory_cache.set(key, value_obj, ttl=self.default_ttl)
                        
                        return value_obj
                    except json.JSONDecodeError:
                        # 如果不是JSON，直接返回字符串
                        logger.debug(f"Cache hit (redis, non-JSON): {key}")
                        return value_str
            
            logger.debug(f"Cache miss: {key}")
            return None
        except Exception as e:
            logger.error(f"Error getting cache for key {key}: {str(e)}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 要缓存的值
            ttl: 过期时间（秒），如果不指定则使用默认值
        
        Returns:
            是否成功设置
        """
        if not self.initialized:
            logger.warning("Cache manager not initialized, skipping set operation")
            return False
        
        if ttl is None:
            ttl = self.default_ttl
        
        try:
            # 转换为JSON字符串
            if isinstance(value, (dict, list, tuple)) or not isinstance(value, (str, bytes, int, float, bool, type(None))):
                value_str = json.dumps(value)
            else:
                value_str = str(value)
                
            # 设置Redis缓存
            if self.redis_client:
                await self.redis_client.set(key, value_str, expire=ttl)
            
            # 设置内存缓存
            if self.memory_cache:
                if isinstance(value, (str, bytes)):
                    try:
                        # 尝试解析JSON
                        value_obj = json.loads(value)
                        await self.memory_cache.set(key, value_obj, ttl=ttl)
                    except json.JSONDecodeError:
                        await self.memory_cache.set(key, value, ttl=ttl)
                else:
                    await self.memory_cache.set(key, value, ttl=ttl)
            
            logger.debug(f"Cache set: {key}, TTL: {ttl}s")
            return True
        except Exception as e:
            logger.error(f"Error setting cache for key {key}: {str(e)}")
            return False
    
    async def delete(self, key: str) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存键
        
        Returns:
            是否成功删除
        """
        if not self.initialized:
            logger.warning("Cache manager not initialized, skipping delete operation")
            return False
        
        try:
            # 删除Redis缓存
            if self.redis_client:
                await self.redis_client.delete(key)
            
            # 删除内存缓存
            if self.memory_cache:
                await self.memory_cache.delete(key)
            
            logger.debug(f"Cache deleted: {key}")
            return True
        except Exception as e:
            logger.error(f"Error deleting cache for key {key}: {str(e)}")
            return False
    
    async def clear(self, pattern: str = "*") -> bool:
        """
        清除指定模式的缓存
        
        Args:
            pattern: 键模式，默认清除所有缓存
        
        Returns:
            是否成功清除
        """
        if not self.initialized:
            logger.warning("Cache manager not initialized, skipping clear operation")
            return False
        
        try:
            # 清除Redis缓存
            if self.redis_client:
                # 获取匹配的键
                keys = []
                cur = b'0'
                while cur:
                    cur, keys_batch = await self.redis_client.scan(cur, match=pattern)
                    keys.extend(keys_batch)
                
                # 如果有匹配的键，则删除
                if keys:
                    await self.redis_client.delete(*keys)
                    logger.info(f"Cleared {len(keys)} keys from Redis matching pattern: {pattern}")
            
            # 清除内存缓存
            if self.memory_cache:
                await self.memory_cache.clear()
                logger.info(f"Cleared memory cache")
            
            return True
        except Exception as e:
            logger.error(f"Error clearing cache with pattern {pattern}: {str(e)}")
            return False
    
    async def exists(self, key: str) -> bool:
        """
        检查缓存是否存在
        
        Args:
            key: 缓存键
        
        Returns:
            缓存是否存在
        """
        if not self.initialized:
            logger.warning("Cache manager not initialized, skipping exists operation")
            return False
        
        try:
            # 首先检查内存缓存
            if self.memory_cache:
                exists = await self.memory_cache.exists(key)
                if exists:
                    return True
            
            # 然后检查Redis缓存
            if self.redis_client:
                exists = await self.redis_client.exists(key)
                return exists > 0
            
            return False
        except Exception as e:
            logger.error(f"Error checking cache existence for key {key}: {str(e)}")
            return False
    
    async def ttl(self, key: str) -> int:
        """
        获取缓存剩余过期时间
        
        Args:
            key: 缓存键
        
        Returns:
            剩余秒数，如果键不存在或已过期，则返回-1
        """
        if not self.initialized:
            logger.warning("Cache manager not initialized, skipping ttl operation")
            return -1
        
        try:
            # 获取Redis缓存TTL
            if self.redis_client:
                ttl = await self.redis_client.ttl(key)
                return ttl
            
            return -1
        except Exception as e:
            logger.error(f"Error getting TTL for key {key}: {str(e)}")
            return -1
    
    async def incr(self, key: str, amount: int = 1) -> int:
        """
        增加计数器值
        
        Args:
            key: 缓存键
            amount: 增加的数量
        
        Returns:
            增加后的值，如果操作失败则返回-1
        """
        if not self.initialized:
            logger.warning("Cache manager not initialized, skipping incr operation")
            return -1
        
        try:
            # 增加Redis计数器
            if self.redis_client:
                value = await self.redis_client.incrby(key, amount)
                
                # 同步到内存缓存
                if self.memory_cache:
                    await self.memory_cache.set(key, value, ttl=self.default_ttl)
                
                return value
            
            return -1
        except Exception as e:
            logger.error(f"Error incrementing counter for key {key}: {str(e)}")
            return -1
    
    async def decr(self, key: str, amount: int = 1) -> int:
        """
        减少计数器值
        
        Args:
            key: 缓存键
            amount: 减少的数量
        
        Returns:
            减少后的值，如果操作失败则返回-1
        """
        if not self.initialized:
            logger.warning("Cache manager not initialized, skipping decr operation")
            return -1
        
        try:
            # 减少Redis计数器
            if self.redis_client:
                value = await self.redis_client.decrby(key, amount)
                
                # 同步到内存缓存
                if self.memory_cache:
                    await self.memory_cache.set(key, value, ttl=self.default_ttl)
                
                return value
            
            return -1
        except Exception as e:
            logger.error(f"Error decrementing counter for key {key}: {str(e)}")
            return -1 