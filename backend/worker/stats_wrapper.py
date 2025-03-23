#!/usr/bin/env python
"""
源统计信息自动更新包装器

此模块实现一个包装器，在调用源适配器的fetch方法后自动更新统计信息。
"""
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional
import datetime

from app.db.session import SessionLocal
from app.crud.source_stats import update_source_status, get_latest_stats, create_source_stats
from app.crud.source import get_source, update_source
from worker.sources.base import NewsItemModel

logger = logging.getLogger(__name__)

class StatsUpdater:
    """
    源统计信息更新器
    自动跟踪源适配器的调用情况并更新统计信息
    """

    def __init__(self, enabled: bool = True, update_interval: int = 900):
        """
        初始化统计信息更新器
        
        Args:
            enabled: 是否启用统计更新
            update_interval: 统计信息更新间隔（秒），避免过于频繁的数据库操作，默认15分钟
        """
        self.enabled = enabled
        self.update_interval = update_interval
        self.last_update: Dict[str, float] = {}
        self.stats_cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        # 存储无效源ID的集合，避免重复检查已知不存在的源
        self._invalid_source_ids = set()

    async def wrap_fetch(self, source_id: str, fetch_func, api_type: str = "internal", *args, **kwargs) -> List[NewsItemModel]:
        """
        包装源适配器的fetch方法，自动更新统计信息
        
        Args:
            source_id: 源ID
            fetch_func: 源适配器的fetch方法
            api_type: API调用类型，默认为internal（内部调用）
            
        Returns:
            获取的新闻列表
        """
        # 从源对象的source_id属性获取，可能使用下划线而不是连字符
        # 我们在这里不转换，保持原始ID，在更新统计信息时再处理兼容性
        logger.info(f"StatsUpdater: 开始包装 {source_id} 的fetch方法，API类型: {api_type}")
        
        if not self.enabled:
            logger.warning(f"StatsUpdater: 统计更新器已禁用，不会更新 {source_id} 的统计信息")
            return await fetch_func(*args, **kwargs)
        
        # 记录开始时间
        start_time = time.time()
        success = True
        error_message = None
        result = []
        
        try:
            # 调用原始的fetch方法
            logger.info(f"StatsUpdater: 调用 {source_id} 的fetch方法")
            result = await fetch_func(*args, **kwargs)
            logger.info(f"StatsUpdater: {source_id} 的fetch方法调用成功，获得 {len(result)} 条新闻")
            return result
        except Exception as e:
            success = False
            error_message = str(e)
            logger.error(f"源 {source_id} 调用fetch方法出错: {error_message}")
            raise
        finally:
            # 不管成功还是失败，都更新统计信息
            end_time = time.time()
            response_time = (end_time - start_time) * 1000  # 转换为毫秒
            logger.info(f"StatsUpdater: 更新 {source_id} 的统计信息，用时 {response_time:.2f}ms，API类型: {api_type}")
            await self._update_stats(source_id, success, response_time, len(result), error_message, api_type)
    
    def _normalize_source_id(self, source_id: str) -> str:
        """
        标准化源ID，确保与数据库中的ID格式一致
        
        Args:
            source_id: 原始源ID
            
        Returns:
            标准化后的源ID
        """
        # 与数据库中的ID格式保持一致：
        # 1. 如果是zhihu_daily这样的ID，转换为zhihu-daily
        # 2. 如果已经是连字符格式，则保持不变
        if "_" in source_id:
            # 尝试两种格式的ID，先尝试原始格式
            return source_id
        return source_id
    
    async def _update_stats(self, source_id: str, success: bool, response_time: float, 
                           news_count: int = 0, error_message: Optional[str] = None,
                           api_type: str = "internal") -> None:
        """
        更新源统计信息
        
        Args:
            source_id: 源ID
            success: 是否成功
            response_time: 响应时间（毫秒）
            news_count: 获取到的新闻数量
            error_message: 错误信息
            api_type: API调用类型，默认为internal（内部调用）
        """
        if not self.enabled:
            return
        
        # 检查是否是已知无效的源ID
        if source_id in self._invalid_source_ids:
            logger.debug(f"跳过更新统计信息：{source_id} 是已知的无效源ID")
            return
            
        # 使用锁避免并发问题
        async with self._lock:
            # 检查是否需要更新
            current_time = time.time()
            last_update_time = self.last_update.get(source_id, 0)
            
            # 如果自上次更新以来还不到指定时间，则只更新缓存
            # 但是如果发生错误，始终更新数据库
            should_update_db = (current_time - last_update_time) >= self.update_interval or not success
            
            # 获取或初始化统计数据
            cache_key = f"{source_id}:{api_type}"
            stats = self.stats_cache.get(cache_key, {
                "success_count": 0,
                "error_count": 0,
                "total_requests": 0,
                "total_response_time": 0,
                "news_count": 0,
                "last_error": None,
                "last_response_time": 0,
                "api_type": api_type
            })
            
            # 更新统计数据
            stats["total_requests"] += 1
            stats["total_response_time"] += response_time
            stats["last_response_time"] = response_time
            stats["news_count"] += news_count
            
            if success:
                stats["success_count"] += 1
            else:
                stats["error_count"] += 1
                stats["last_error"] = error_message
            
            # 更新缓存
            self.stats_cache[cache_key] = stats
            
            logger.debug(f"StatsUpdater: 已更新缓存中 {source_id} 的统计信息: 总请求 {stats['total_requests']}, "
                        f"成功 {stats['success_count']}, 失败 {stats['error_count']}, 新闻 {stats['news_count']}, "
                        f"API类型: {api_type}")
            
            # 如果需要更新数据库
            if should_update_db:
                try:
                    # 计算成功率和平均响应时间
                    success_rate = stats["success_count"] / stats["total_requests"] if stats["total_requests"] > 0 else 0
                    avg_response_time = stats["total_response_time"] / stats["total_requests"] if stats["total_requests"] > 0 else 0
                    
                    # 使用同步方式创建数据库会话
                    db = None
                    try:
                        # 创建数据库会话
                        db = SessionLocal()
                        
                        # 尝试使用原始ID获取源
                        db_source = get_source(db, source_id)
                        
                        # 如果找不到，尝试使用转换后的ID
                        if not db_source and "_" in source_id:
                            # 尝试将下划线替换为连字符
                            alt_source_id = source_id.replace("_", "-")
                            db_source = get_source(db, alt_source_id)
                            if db_source:
                                # 如果找到了，更新源ID
                                source_id = alt_source_id
                                logger.info(f"找到替代源ID: {source_id} (原始ID: {source_id})")
                        
                        # 如果源不存在，记录它并跳过更新
                        if not db_source:
                            logger.warning(f"源 {source_id} 不存在于数据库中，跳过统计更新")
                            self._invalid_source_ids.add(source_id)
                            return
                            
                        # 获取现有统计数据，指定api_type
                        existing_stats = get_latest_stats(db, source_id, api_type)
                        
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
                                avg_response_time = (existing_stats.avg_response_time * existing_stats.total_requests + 
                                                 stats["total_response_time"]) / (existing_stats.total_requests + stats["total_requests"])
                        
                        # 更新源状态
                        source_status = "active" if success else "error"
                        
                        if not success and error_message:
                            # 记录错误信息
                            db_source.status = source_status
                            db_source.last_error = error_message
                            db_source.error_count = error_count
                            db_source.last_update = datetime.datetime.fromtimestamp(current_time)
                            db.commit()
                        else:
                            # 更新状态
                            db_source.status = source_status
                            db_source.last_update = datetime.datetime.fromtimestamp(current_time)
                            db_source.news_count = db_source.news_count + stats["news_count"]
                            db.commit()
                        
                        # 使用create_source_stats创建新的统计记录，传递api_type
                        create_source_stats(db, source_id, 
                                         success_rate=success_rate,
                                         avg_response_time=avg_response_time,
                                         last_response_time=stats["last_response_time"],
                                         total_requests=total_requests,
                                         error_count=error_count,
                                         news_count=stats["news_count"],
                                         api_type=api_type)
                        
                        db.commit()
                        
                        # 重置缓存，避免重复累加
                        self.stats_cache[cache_key] = {
                            "success_count": 0,
                            "error_count": 0,
                            "total_requests": 0,
                            "total_response_time": 0,
                            "news_count": 0,
                            "last_error": None,
                            "last_response_time": 0,
                            "api_type": api_type
                        }
                        
                        # 更新最后更新时间
                        self.last_update[source_id] = current_time
                        
                        logger.info(f"StatsUpdater: 已更新数据库中 {source_id} 的统计信息: "
                                   f"成功率 {success_rate:.2f}, 平均响应时间 {avg_response_time:.2f}ms, "
                                   f"总请求 {total_requests}, 错误 {error_count}, API类型: {api_type}")
                    finally:
                        if db:
                            db.close()
                except Exception as e:
                    logger.exception(f"更新 {source_id} 的统计信息失败: {str(e)}")


# 创建统计更新器实例
stats_updater = StatsUpdater() 