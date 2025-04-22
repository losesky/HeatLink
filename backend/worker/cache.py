import logging
import json
import pickle
import time
from typing import Dict, Any, Optional, List, Union

import aioredis
from app.core.logging_config import get_cache_logger

# 保留主日志记录器用于关键错误信息
logger = logging.getLogger(__name__)
# 使用缓存专用日志记录器
cache_logger = get_cache_logger()


class CacheManager:
    """
    缓存管理器
    支持内存缓存和Redis缓存
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        enable_memory_cache: bool = True,
        default_ttl: int = 900,  # 默认缓存时间，单位秒，默认15分钟
        verbose_logging: bool = False  # 是否启用详细日志记录
    ):
        self.redis_url = redis_url
        self.enable_memory_cache = enable_memory_cache
        self.default_ttl = default_ttl
        self.verbose_logging = verbose_logging
        
        # 内存缓存
        self.memory_cache: Dict[str, Dict[str, Any]] = {}
        
        # Redis连接
        self.redis = None
        
        # 初始化标志
        self.initialized = False
    
    def _debug_log(self, message: str):
        """仅在启用详细日志的情况下记录DEBUG日志"""
        if self.verbose_logging:
            cache_logger.debug(f"[CACHE] {message}")
    
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
                # 记录重要信息到主日志，但格式更简洁
                logger.info(f"Redis连接已建立: {self.redis_url}")
                # 详细信息记录到缓存专用日志
                cache_logger.info(f"[BASE-CACHE-INIT] 已连接到Redis: {self.redis_url}")
            except Exception as e:
                # 错误信息保留在主日志中，确保错误不被忽略
                error_msg = f"Redis连接失败: {str(e)}"
                logger.error(error_msg)
                cache_logger.error(f"[BASE-CACHE-INIT] {error_msg}")
                self.redis = None
        
        # 初始化完成
        self.initialized = True
        # 简化主日志中的信息
        logger.info(f"缓存管理器初始化完成: 内存缓存={self.enable_memory_cache}, Redis={self.redis is not None}")
        # 详细信息记录到缓存专用日志
        cache_logger.info(f"[BASE-CACHE-INIT] 缓存管理器初始化完成，内存缓存: {self.enable_memory_cache}, Redis: {self.redis is not None}")
    
    async def close(self):
        """
        关闭缓存管理器
        """
        # 如果有Redis连接，则关闭
        if self.redis:
            self.redis.close()
            await self.redis.wait_closed()
            self.redis = None
            # 简化主日志信息
            logger.info("Redis连接已关闭")
            # 详细信息记录到缓存专用日志
            cache_logger.info("[BASE-CACHE-INIT] Redis连接已关闭")
        
        # 清空内存缓存
        self.memory_cache.clear()
        
        # 重置初始化标志
        self.initialized = False
        
        # 简化主日志信息
        logger.info("缓存管理器已关闭")
        # 详细信息记录到缓存专用日志
        cache_logger.info("[BASE-CACHE-INIT] 缓存管理器已关闭")
    
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
                    self._debug_log(f"内存缓存命中: {key}")
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
                        
                        self._debug_log(f"Redis缓存命中: {key}")
                        return result
                    except Exception as e:
                        # 错误信息保留在主日志中
                        error_msg = f"Redis数据反序列化失败: {str(e)}"
                        logger.error(error_msg)
                        cache_logger.error(f"[CACHE-ERROR] {error_msg}")
            except Exception as e:
                # 错误信息保留在主日志中
                error_msg = f"从Redis获取数据失败: {str(e)}"
                logger.error(error_msg)
                cache_logger.error(f"[CACHE-ERROR] {error_msg}")
        
        # 缓存未命中
        self._debug_log(f"缓存未命中: {key}")
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
                
                # 只记录操作成功的简要日志，如果是缓存批量操作，避免过多日志
                if self.verbose_logging:
                    self._debug_log(f"Redis缓存已更新: {key}, TTL: {ttl}秒")
                elif key.startswith("sources:all") or key.startswith("categories:all"):
                    # 只记录关键缓存操作的日志到缓存专用日志
                    cache_logger.info(f"[CACHE-UPDATE] 关键数据已更新: {key}")
            except Exception as e:
                # 错误信息保留在主日志中
                error_msg = f"向Redis存入数据失败: {str(e)}"
                logger.error(error_msg)
                cache_logger.error(f"[CACHE-ERROR] {error_msg}")
    
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
                self._debug_log(f"Redis缓存已删除: {key}")
            except Exception as e:
                # 错误信息保留在主日志中
                error_msg = f"从Redis删除数据失败: {str(e)}"
                logger.error(error_msg)
                cache_logger.error(f"[CACHE-ERROR] {error_msg}")
    
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
                    # 保留简要信息到主日志
                    logger.info(f"已清空Redis缓存, 模式: {pattern}, 数量: {len(keys)}")
                    # 详细信息记录到缓存专用日志
                    cache_logger.info(f"[CACHE-CLEAR] 已清空Redis缓存, 模式: {pattern}, 数量: {len(keys)}")
            except Exception as e:
                # 错误信息保留在主日志中
                error_msg = f"清空Redis缓存失败: {str(e)}"
                logger.error(error_msg)
                cache_logger.error(f"[CACHE-ERROR] {error_msg}")
    
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
                }
                
                # 记录到缓存专用日志
                cache_logger.info(f"[CACHE-STATS] Redis统计信息: 键数量={len(keys)}, 内存使用={info.get('used_memory_human', '')}")
            except Exception as e:
                # 错误信息保留在主日志中
                error_msg = f"获取Redis统计信息失败: {str(e)}"
                logger.error(error_msg)
                cache_logger.error(f"[CACHE-ERROR] {error_msg}")
        
        return stats 

# 创建一个全局的缓存管理器实例供其他模块导入使用
cache_manager = CacheManager() 