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
from app.crud.source import get_source, update_source, get_source_by_alias
from worker.sources.base import NewsItemModel

logger = logging.getLogger(__name__)

class StatsUpdater:
    """
    源统计信息更新器
    自动跟踪源适配器的调用情况并更新统计信息
    """

    def __init__(self, enabled: bool = True, update_interval: int = 3600, retry_count: int = 3, retry_delay: int = 1):
        """
        初始化统计信息更新器
        
        Args:
            enabled: 是否启用统计更新
            update_interval: 统计信息更新间隔（秒），避免过于频繁的数据库操作，默认1小时
            retry_count: 重试次数
            retry_delay: 重试延迟（秒）
        """
        self.enabled = enabled
        self.update_interval = update_interval
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.last_update: Dict[str, float] = {}
        self.stats_cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        # 存储无效源ID的集合，避免重复检查已知不存在的源
        self._invalid_source_ids = set()
        # 记录错误源统计信息直到下次更新
        self._error_sources: Dict[str, Any] = {}

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
            result = await fetch_func(*args, **kwargs)
            news_count = len(result) if result else 0
            logger.info(f"StatsUpdater: {source_id} 的fetch方法调用成功，获得 {news_count} 条新闻")
            return result
        except Exception as e:
            success = False
            error_message = str(e)
            logger.error(f"StatsUpdater: 源 {source_id} 调用fetch方法出错: {error_message}")
            raise
        finally:
            # 不管成功还是失败，都更新统计信息
            end_time = time.time()
            response_time = (end_time - start_time) * 1000  # 转换为毫秒
            news_count = len(result) if result else 0
            
            # 更新内存中的统计
            await self._update_memory_stats(source_id, success, response_time, news_count, error_message, api_type)
            
            # 如果需要，异步更新数据库统计
            if await self._should_update_db(source_id):
                try:
                    # 使用后台任务更新数据库统计，避免阻塞主流程
                    asyncio.create_task(self._update_db_stats_with_retry(source_id, api_type))
                except Exception as db_err:
                    logger.error(f"StatsUpdater: 创建数据库统计更新任务失败: {str(db_err)}")
    
    async def _update_db_stats_with_retry(self, source_id: str, api_type: str) -> None:
        """带重试机制的数据库统计更新"""
        retry_count = self.retry_count
        last_error = None
        
        while retry_count > 0:
            try:
                await self._update_db_stats(source_id, api_type)
                return  # 成功就返回
            except Exception as e:
                last_error = e
                retry_count -= 1
                if retry_count > 0:
                    logger.warning(f"StatsUpdater: 更新 {source_id} 统计失败，将在 {self.retry_delay} 秒后重试: {str(e)}")
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(f"StatsUpdater: 更新 {source_id} 统计达到最大重试次数，放弃: {str(e)}")
                    
        # 如果所有重试都失败，记录最后一个错误
        if last_error:
            logger.error(f"StatsUpdater: 所有重试都失败，最后错误: {str(last_error)}")
    
    async def _update_db_stats(self, source_id: str, api_type: str = "internal") -> None:
        """更新数据库统计，使用独立的事务和简化的错误处理"""
        cache_key = f"{source_id}:{api_type}"
        stats = self.stats_cache.get(cache_key, {})
        if not stats:
            return
            
        # 使用一个新的会话和事务
        db = None
        try:
            # 创建单独的数据库会话
            db = SessionLocal()
            
            # 尝试获取源
            db_source = None
            source_id_found = None
            
            # 尝试所有可能的ID格式
            possible_ids = [source_id]
            
            # 添加连字符/下划线转换的变体
            if "_" in source_id:
                possible_ids.append(source_id.replace("_", "-"))
            elif "-" in source_id:
                possible_ids.append(source_id.replace("-", "_"))
            
            # 尝试每个可能的ID
            for try_id in possible_ids:
                try:
                    # 直接尝试ID
                    db_source = get_source(db, try_id)
                    if db_source:
                        source_id_found = try_id
                        break
                except Exception:
                    continue
                    
                try:
                    # 尝试作为别名查找
                    db_source = get_source_by_alias(db, try_id)
                    if db_source:
                        source_id_found = db_source.id
                        break
                except Exception:
                    continue
            
            # 如果找不到源，记录为无效并返回
            if not db_source:
                logger.warning(f"StatsUpdater: 源 {source_id} 不存在于数据库中，标记为无效")
                self._invalid_source_ids.add(source_id)
                return
                
            # 使用找到的ID
            source_id = source_id_found or source_id
                
            # 计算统计数据
            success_rate = stats["success_count"] / stats["total_requests"] if stats["total_requests"] > 0 else 0
            avg_response_time = stats["total_response_time"] / stats["total_requests"] if stats["total_requests"] > 0 else 0
            
            # 更新源状态（简化版本）
            if source_id in self._error_sources:
                db_source.status = "error"
                db_source.last_error = self._error_sources[source_id]["error"]
                db_source.error_count = db_source.error_count + stats["error_count"] if db_source.error_count else stats["error_count"]
            else:
                db_source.status = "active"
                
            db_source.last_updated = datetime.datetime.now()
            # 更新源的news_count字段，但不累加，直接使用最新值
            db_source.news_count = stats["news_count"]
            
            # 提交源状态更新
            db.commit()
            
            # 创建统计记录（简单版本）
            try:
                # 增加累积的统计量，从最新的历史记录中获取
                # 先尝试获取最近的统计记录，以累加total_requests
                latest_stats = get_latest_stats(db, source_id, api_type)
                total_requests = stats["total_requests"]
                if latest_stats:
                    # 把当前请求数加到上一次的总请求数上，实现累加效果
                    total_requests = latest_stats.total_requests + stats["total_requests"]
                
                create_source_stats(
                    db, source_id,
                    success_rate=success_rate,
                    avg_response_time=avg_response_time,
                    last_response_time=stats["last_response_time"],
                    total_requests=total_requests,  # 使用累加后的请求总数
                    error_count=stats["error_count"],
                    news_count=stats["news_count"],
                    api_type=api_type
                )
                db.commit()
                
                # 清除错误源记录
                if source_id in self._error_sources:
                    del self._error_sources[source_id]
                
                # 更新最后更新时间
                self.last_update[source_id] = time.time()
                
                # 重置统计缓存
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
                
                logger.info(f"StatsUpdater: 成功更新数据库中 {source_id} 的统计信息")
            except Exception as stats_err:
                logger.warning(f"StatsUpdater: 创建统计记录失败: {str(stats_err)}")
                db.rollback()
                raise  # 重新抛出异常以触发重试
            
        except Exception as e:
            logger.error(f"StatsUpdater: 更新数据库统计时出错: {str(e)}")
            raise  # 重新抛出异常以触发重试
        finally:
            # 确保关闭会话
            if db:
                try:
                    db.close()
                except Exception:
                    pass
    
    async def _update_memory_stats(self, source_id: str, success: bool, response_time: float, 
                           news_count: int = 0, error_message: Optional[str] = None,
                           api_type: str = "internal") -> None:
        """只更新内存中的统计信息，不访问数据库"""
        async with self._lock:
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
                # 记录错误源，以便稍后处理
                if error_message:
                    self._error_sources[source_id] = {
                        "time": time.time(),
                        "error": error_message
                    }
            
            # 更新缓存
            self.stats_cache[cache_key] = stats
            
            logger.debug(f"StatsUpdater: 已更新缓存中 {source_id} 的统计信息: 总请求 {stats['total_requests']}, "
                        f"成功 {stats['success_count']}, 失败 {stats['error_count']}, 新闻 {stats['news_count']}")
    
    async def _should_update_db(self, source_id: str) -> bool:
        """判断是否应该更新数据库"""
        # 如果是无效源，不更新
        if source_id in self._invalid_source_ids:
            return False
            
        # 如果是错误源，立即更新
        if source_id in self._error_sources:
            return True
            
        # 检查上次更新时间
        current_time = time.time()
        last_update_time = self.last_update.get(source_id, 0)
        should_update = (current_time - last_update_time) >= self.update_interval
        return should_update


# 创建统计更新器实例
# 设置更长的更新间隔（1小时），避免频繁的数据库操作
# 配置重试机制，确保数据库更新稳定性
stats_updater = StatsUpdater(
    enabled=True, 
    update_interval=3600,  # 1小时更新一次
    retry_count=3,         # 出错重试3次
    retry_delay=2          # 每次重试间隔2秒
) 