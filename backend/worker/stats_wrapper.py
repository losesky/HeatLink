#!/usr/bin/env python
"""
源统计信息自动更新包装器

此模块实现一个包装器，在调用源适配器的fetch方法后自动更新统计信息。
"""
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional

from app.db.session import SessionLocal
from app.crud.source_stats import update_source_status, get_latest_stats
from worker.sources.base import NewsItemModel

logger = logging.getLogger(__name__)

class StatsUpdater:
    """
    源统计信息更新器
    自动跟踪源适配器的调用情况并更新统计信息
    """

    def __init__(self, enabled: bool = True, update_interval: int = 3600):
        """
        初始化统计信息更新器
        
        Args:
            enabled: 是否启用统计更新
            update_interval: 统计信息更新间隔（秒），避免过于频繁的数据库操作
        """
        self.enabled = enabled
        self.update_interval = update_interval
        self.last_update: Dict[str, float] = {}
        self.stats_cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def wrap_fetch(self, source_id: str, fetch_func, *args, **kwargs) -> List[NewsItemModel]:
        """
        包装源适配器的fetch方法，自动更新统计信息
        
        Args:
            source_id: 源ID
            fetch_func: 源适配器的fetch方法
            
        Returns:
            获取的新闻列表
        """
        # 规范化源ID（确保使用连字符格式，与数据库一致）
        normalized_source_id = source_id.replace('_', '-')
        logger.info(f"StatsUpdater: 开始包装 {source_id} 的fetch方法 (规范化ID: {normalized_source_id})")
        
        if not self.enabled:
            logger.warning(f"StatsUpdater: 统计更新器已禁用，不会更新 {normalized_source_id} 的统计信息")
            return await fetch_func(*args, **kwargs)
        
        # 记录开始时间
        start_time = time.time()
        success = True
        error_message = None
        
        try:
            # 调用原始的fetch方法
            logger.info(f"StatsUpdater: 调用 {normalized_source_id} 的fetch方法")
            result = await fetch_func(*args, **kwargs)
            logger.info(f"StatsUpdater: {normalized_source_id} 的fetch方法调用成功")
            return result
        except Exception as e:
            success = False
            error_message = str(e)
            logger.error(f"源 {normalized_source_id} 调用fetch方法出错: {error_message}")
            raise
        finally:
            # 不管成功还是失败，都更新统计信息
            end_time = time.time()
            response_time = (end_time - start_time) * 1000  # 转换为毫秒
            logger.info(f"StatsUpdater: 更新 {normalized_source_id} 的统计信息，用时 {response_time:.2f}ms")
            await self._update_stats(normalized_source_id, success, response_time, error_message)
    
    async def _update_stats(self, source_id: str, success: bool, response_time: float, error_message: Optional[str] = None) -> None:
        """
        更新源统计信息
        
        Args:
            source_id: 源ID
            success: 是否成功
            response_time: 响应时间（毫秒）
            error_message: 错误信息
        """
        if not self.enabled:
            return
        
        # 使用锁避免并发问题
        async with self._lock:
            # 检查是否需要更新
            current_time = time.time()
            last_update_time = self.last_update.get(source_id, 0)
            
            # 如果自上次更新以来还不到指定时间，则只更新缓存
            should_update_db = (current_time - last_update_time) >= self.update_interval
            
            # 获取或初始化统计数据
            stats = self.stats_cache.get(source_id, {
                "success_count": 0,
                "error_count": 0,
                "total_requests": 0,
                "total_response_time": 0,
                "last_error": None
            })
            
            # 更新统计数据
            stats["total_requests"] += 1
            if success:
                stats["success_count"] += 1
            else:
                stats["error_count"] += 1
                stats["last_error"] = error_message
            
            stats["total_response_time"] += response_time
            
            # 更新缓存
            self.stats_cache[source_id] = stats
            
            logger.debug(f"StatsUpdater: 已更新缓存中 {source_id} 的统计信息: 总请求 {stats['total_requests']}, 成功 {stats['success_count']}, 失败 {stats['error_count']}")
            
            # 如果需要更新数据库
            if should_update_db:
                try:
                    # 计算成功率和平均响应时间
                    success_rate = stats["success_count"] / stats["total_requests"] if stats["total_requests"] > 0 else 0
                    avg_response_time = stats["total_response_time"] / stats["total_requests"] if stats["total_requests"] > 0 else 0
                    
                    # 创建数据库会话
                    db = SessionLocal()
                    try:
                        # 获取现有统计数据
                        existing_stats = get_latest_stats(db, source_id)
                        
                        # 累加现有统计数据（如果存在）
                        total_requests = stats["total_requests"]
                        error_count = stats["error_count"]
                        
                        if existing_stats:
                            total_requests += existing_stats.total_requests
                            error_count += existing_stats.error_count
                            
                            # 计算成功率（考虑历史数据）
                            success_rate = (total_requests - error_count) / total_requests if total_requests > 0 else 0
                            
                            # 计算平均响应时间（考虑历史数据）
                            if existing_stats.total_requests > 0:
                                avg_response_time = (
                                    (existing_stats.avg_response_time * existing_stats.total_requests) + 
                                    stats["total_response_time"]
                                ) / (existing_stats.total_requests + stats["total_requests"])
                        
                        # 更新数据库
                        update_source_status(
                            db=db,
                            source_id=source_id,
                            success_rate=success_rate,
                            avg_response_time=avg_response_time,
                            total_requests=total_requests,
                            error_count=error_count,
                            last_error=stats["last_error"]
                        )
                        
                        logger.info(f"StatsUpdater: 已更新数据库中源 {source_id} 的统计信息：总请求 {total_requests}, 成功率 {success_rate:.2f}，平均响应时间 {avg_response_time:.2f}ms")
                        
                        # 重置缓存的统计数据
                        self.stats_cache[source_id] = {
                            "success_count": 0,
                            "error_count": 0,
                            "total_requests": 0,
                            "total_response_time": 0,
                            "last_error": None
                        }
                        
                        # 更新最后更新时间
                        self.last_update[source_id] = current_time
                        
                    finally:
                        db.close()
                
                except Exception as e:
                    logger.error(f"StatsUpdater: 更新源 {source_id} 的统计信息时出错: {str(e)}")
            else:
                logger.debug(f"StatsUpdater: 暂不更新数据库中 {source_id} 的统计信息，距离上次更新仅 {current_time - last_update_time:.1f}秒")


# 创建全局单例
stats_updater = StatsUpdater(update_interval=0)  # 设置为0秒强制立即更新数据库 