"""
缓存增强模块

为所有新闻源适配器提供标准化的缓存保护机制和监控功能。
此模块可以作为装饰器应用于现有新闻源类，也可以通过注入方式增强现有源。
"""

import logging
import time
import functools
import inspect
from typing import List, Dict, Any, Optional, Type, Callable, Union, TypeVar
import datetime
import asyncio
from app.core.logging_config import get_cache_logger

# 设置日志
logger = logging.getLogger(__name__)
# 使用缓存专用日志记录器
cache_logger = get_cache_logger()

# 类型提示
T = TypeVar('T')
NewsItemModel = TypeVar('NewsItemModel')
NewsSource = TypeVar('NewsSource')

class CacheProtectionStats:
    """缓存保护统计数据类"""
    
    def __init__(self):
        """初始化缓存保护统计"""
        self.empty_protection_count = 0    # 空结果保护次数
        self.error_protection_count = 0    # 错误保护次数
        self.shrink_protection_count = 0   # 数量锐减保护次数
        self.last_protection_time = 0      # 最后一次保护时间
        self.protection_history = []       # 保护历史记录(最多保留20条)
        self.max_history = 20
    
    def record_empty_protection(self, source_id: str, cache_size: int) -> None:
        """记录空结果保护事件"""
        self.empty_protection_count += 1
        self.last_protection_time = time.time()
        self._add_history_entry({
            "time": time.time(),
            "type": "empty_protection",
            "source_id": source_id,
            "cache_size": cache_size
        })
    
    def record_error_protection(self, source_id: str, error: str, cache_size: int) -> None:
        """记录错误保护事件"""
        self.error_protection_count += 1
        self.last_protection_time = time.time()
        self._add_history_entry({
            "time": time.time(),
            "type": "error_protection",
            "source_id": source_id,
            "error": error,
            "cache_size": cache_size
        })
    
    def record_shrink_protection(self, source_id: str, old_size: int, new_size: int) -> None:
        """记录数据量锐减保护事件"""
        self.shrink_protection_count += 1
        self.last_protection_time = time.time()
        self._add_history_entry({
            "time": time.time(),
            "type": "shrink_protection",
            "source_id": source_id,
            "old_size": old_size,
            "new_size": new_size,
            "reduction_ratio": (old_size - new_size) / old_size if old_size > 0 else 0
        })
    
    def _add_history_entry(self, entry: Dict[str, Any]) -> None:
        """添加历史记录项，保持历史记录大小"""
        self.protection_history.append(entry)
        if len(self.protection_history) > self.max_history:
            self.protection_history = self.protection_history[-self.max_history:]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "empty_protection_count": self.empty_protection_count,
            "error_protection_count": self.error_protection_count,
            "shrink_protection_count": self.shrink_protection_count,
            "total_protection_count": (
                self.empty_protection_count + 
                self.error_protection_count + 
                self.shrink_protection_count
            ),
            "last_protection_time": self.last_protection_time,
            "recent_protections": self.protection_history[-5:] if self.protection_history else []
        }

class CacheMetrics:
    """缓存性能指标类"""
    
    def __init__(self):
        """初始化缓存性能指标"""
        self.empty_result_count = 0       # 空结果次数
        self.cache_hit_count = 0          # 缓存命中次数
        self.cache_miss_count = 0         # 缓存未命中次数
        self.fetch_error_count = 0        # 获取错误次数
        self.cache_update_count = 0       # 缓存更新次数
        self.last_cache_size = 0          # 最后一次缓存大小
        self.max_cache_size = 0           # 历史最大缓存大小
        self.last_fetch_time = 0          # 最后一次获取时间
        self.last_fetch_duration = 0      # 最后一次获取耗时
    
    def record_cache_hit(self) -> None:
        """记录缓存命中"""
        self.cache_hit_count += 1
    
    def record_cache_miss(self) -> None:
        """记录缓存未命中"""
        self.cache_miss_count += 1
    
    def record_empty_result(self) -> None:
        """记录空结果"""
        self.empty_result_count += 1
    
    def record_fetch_error(self) -> None:
        """记录获取错误"""
        self.fetch_error_count += 1
    
    def record_cache_update(self, cache_size: int) -> None:
        """记录缓存更新"""
        self.cache_update_count += 1
        self.last_cache_size = cache_size
        if cache_size > self.max_cache_size:
            self.max_cache_size = cache_size
    
    def record_fetch(self, duration: float) -> None:
        """记录获取操作"""
        self.last_fetch_time = time.time()
        self.last_fetch_duration = duration
    
    def get_hit_ratio(self) -> float:
        """获取缓存命中率"""
        total = self.cache_hit_count + self.cache_miss_count
        return self.cache_hit_count / max(1, total)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "cache_hit_count": self.cache_hit_count,
            "cache_miss_count": self.cache_miss_count,
            "hit_ratio": self.get_hit_ratio(),
            "empty_result_count": self.empty_result_count,
            "fetch_error_count": self.fetch_error_count,
            "cache_update_count": self.cache_update_count,
            "current_cache_size": self.last_cache_size,
            "max_cache_size": self.max_cache_size,
            "last_fetch_time": self.last_fetch_time,
            "last_fetch_duration": self.last_fetch_duration
        }

class CacheEnhancer:
    """缓存增强器类"""
    
    def __init__(self, source):
        """
        初始化缓存增强器
        
        Args:
            source: 要增强的新闻源实例
        """
        self.source = source
        
        # 确保源有缓存字段
        if not hasattr(source, '_cached_news_items'):
            source._cached_news_items = []
        
        if not hasattr(source, '_last_cache_update'):
            source._last_cache_update = 0
        
        # 添加缓存保护与监控字段
        if not hasattr(source, '_cache_protection_count'):
            source._cache_protection_count = 0
        
        if not hasattr(source, '_cache_metrics'):
            source._cache_metrics = CacheMetrics()
        elif not isinstance(source._cache_metrics, CacheMetrics):
            source._cache_metrics = CacheMetrics()  # 替换为正确的实例
        
        if not hasattr(source, '_cache_protection_stats'):
            source._cache_protection_stats = CacheProtectionStats()
        elif not isinstance(source._cache_protection_stats, CacheProtectionStats):
            source._cache_protection_stats = CacheProtectionStats()  # 替换为正确的实例
            
        # 保存原始方法引用
        self._original_get_news = source.get_news
        self._original_is_cache_valid = source.is_cache_valid
        self._original_update_cache = source.update_cache
        self._original_clear_cache = source.clear_cache
        self._original_fetch = source.fetch
        
        # 用增强版本替换方法
        source.get_news = self._enhanced_get_news
        source.cache_status = self._cache_status
    
    async def _enhanced_get_news(self, force_update: bool = False) -> List[NewsItemModel]:
        """
        增强版获取新闻方法，添加缓存保护机制
        
        Args:
            force_update: 是否强制更新
            
        Returns:
            新闻项列表
        """
        source = self.source
        start_time = time.time()
        
        try:
            # 获取当前缓存状态
            current_cache_size = len(source._cached_news_items) if hasattr(source, '_cached_news_items') and source._cached_news_items else 0
            
            # 记录开始获取的日志
            cache_logger.debug(f"[CACHE-MONITOR] {source.source_id}: 开始获取新闻, force_update={force_update}")
            cache_logger.debug(f"[CACHE-MONITOR] {source.source_id}: 缓存状态: 条目数={current_cache_size}, 上次更新={source._last_cache_update}")
            
            # 设置决策原因，用于日志记录
            if force_update:
                cache_decision = "强制更新"
                source._cache_metrics.record_cache_miss()
            elif not source.is_cache_valid():
                cache_decision = "缓存无效"
                source._cache_metrics.record_cache_miss()
            else:
                cache_decision = "使用缓存"
                source._cache_metrics.record_cache_hit()
            
            # 如果需要更新缓存 - 强制更新或缓存无效
            if force_update or not source.is_cache_valid():
                cache_logger.info(f"[CACHE-DEBUG] {source.source_id}: 需要更新数据 ({cache_decision})")
                
                try:
                    # 调用原始获取方法
                    news_items = await self._original_fetch()
                    
                    # 增强的缓存保护: 如果fetch返回空列表但缓存中有数据，保留现有缓存
                    if not news_items and hasattr(source, '_cached_news_items') and source._cached_news_items:
                        logger.debug(f"缓存保护触发: {source.source_id} - 使用现有缓存替代空结果")
                        cache_logger.warning(f"[CACHE-PROTECTION] {source.source_id}: fetch()返回空列表，但缓存中有 {len(source._cached_news_items)} 条数据，将使用缓存")
                        
                        # 记录缓存保护统计
                        source._cache_protection_count += 1
                        source._cache_metrics.record_empty_result()
                        source._cache_protection_stats.record_empty_protection(
                            source.source_id, len(source._cached_news_items)
                        )
                        
                        # 使用缓存的结果，不更新缓存
                        news_items = source._cached_news_items.copy()
                        
                        # 如果频繁发生保护操作，记录警告
                        if source._cache_protection_count > 3:
                            logger.warning(f"缓存保护频繁触发: {source.source_id} - 已触发 {source._cache_protection_count} 次")
                            cache_logger.warning(f"[CACHE-ALERT] {source.source_id}: 已触发缓存保护 {source._cache_protection_count} 次，可能需要检查数据源")
                    
                    # 增强的缓存保护：如果新闻条目数量相比缓存大幅减少（超过70%），使用缓存
                    elif (current_cache_size > 5 and len(news_items) > 0 and 
                          len(news_items) < current_cache_size * 0.3):
                        logger.debug(f"缓存保护触发: {source.source_id} - 新数据数量大幅减少")
                        cache_logger.warning(f"[CACHE-PROTECTION] {source.source_id}: fetch()返回 {len(news_items)} 条数据，比缓存中的 {current_cache_size} 条减少了 {(current_cache_size - len(news_items)) / current_cache_size:.1%}，将使用缓存")
                        
                        # 记录缓存保护统计
                        source._cache_protection_stats.record_shrink_protection(
                            source.source_id, current_cache_size, len(news_items)
                        )
                        
                        # 使用缓存的结果，不更新缓存
                        news_items = source._cached_news_items.copy()
                    else:
                        # 正常更新缓存
                        await source.update_cache(news_items)
                        source._cache_metrics.record_cache_update(len(news_items))
                except Exception as e:
                    logger.error(f"获取 {source.source_id} 的新闻时出错: {str(e)}", exc_info=True)
                    source._cache_metrics.record_fetch_error()
                    
                    # 增强的错误处理: 在出错情况下，如果有缓存数据，则使用缓存
                    if hasattr(source, '_cached_news_items') and source._cached_news_items:
                        logger.info(f"使用缓存作为错误恢复: {source.source_id}")
                        cache_logger.warning(f"[CACHE-PROTECTION] {source.source_id}: fetch()出错，使用缓存的 {len(source._cached_news_items)} 条数据")
                        cache_decision = "出错后使用缓存"
                        
                        # 记录缓存保护统计
                        source._cache_protection_stats.record_error_protection(
                            source.source_id, str(e), len(source._cached_news_items)
                        )
                        
                        # 使用缓存的结果
                        news_items = source._cached_news_items.copy()
                    else:
                        news_items = []
            else:
                # 使用缓存数据
                cache_logger.info(f"[CACHE-DEBUG] {source.source_id}: 使用缓存数据，{len(source._cached_news_items)}条，缓存年龄: {time.time() - source._last_cache_update:.2f}秒")
                news_items = source._cached_news_items.copy()
            
            # 记录性能指标
            elapsed = time.time() - start_time
            source._cache_metrics.record_fetch(elapsed)
            
            # 计算性能指标
            cache_logger.debug(f"[CACHE-MONITOR] {source.source_id}: 获取完成，决策={cache_decision}，耗时={elapsed:.3f}秒，获取 {len(news_items)} 条新闻")
            return news_items
        except Exception as e:
            # 如果任何步骤出错，记录异常并返回空列表
            elapsed = time.time() - start_time
            logger.error(f"获取新闻异常: {source.source_id} - {str(e)}", exc_info=True)
            cache_logger.error(f"[CACHE-MONITOR] {source.source_id}: 获取新闻异常: {str(e)}, 耗时={elapsed:.3f}秒", exc_info=True)
            return []
    
    def _cache_status(self) -> Dict[str, Any]:
        """
        获取缓存状态的详细信息，用于监控
        
        Returns:
            包含缓存状态信息的字典
        """
        source = self.source
        
        # 计算缓存年龄
        cache_age = time.time() - source._last_cache_update if source._last_cache_update > 0 else float('inf')
        
        # 构建返回结果
        status = {
            "source_id": source.source_id,
            "source_name": source.name,
            "cache_config": {
                "update_interval": source.update_interval,
                "cache_ttl": source.cache_ttl,
                "adaptive_enabled": getattr(source, 'enable_adaptive', False),
                "current_adaptive_interval": getattr(source, 'adaptive_interval', source.update_interval)
            },
            "cache_state": {
                "has_items": bool(source._cached_news_items),
                "items_count": len(source._cached_news_items) if source._cached_news_items else 0,
                "last_update": source._last_cache_update,
                "cache_age_seconds": cache_age,
                "is_expired": cache_age > source.cache_ttl,
                "valid": source.is_cache_valid()
            },
            "protection_stats": source._cache_protection_stats.to_dict(),
            "metrics": source._cache_metrics.to_dict()
        }
        
        return status

def enhance_source(source: NewsSource) -> NewsSource:
    """
    增强新闻源的缓存机制
    
    Args:
        source: 要增强的新闻源实例
        
    Returns:
        增强后的新闻源实例
    """
    # 创建增强器
    enhancer = CacheEnhancer(source)
    
    # 标记源已被增强
    source._cache_enhanced = True
    
    logger.info(f"[CACHE-ENHANCER] 已增强源 {source.source_id} 的缓存机制")
    return source

def enhance_sources(sources: Dict[str, NewsSource]) -> Dict[str, NewsSource]:
    """
    批量增强多个新闻源的缓存机制
    
    Args:
        sources: 源ID到源实例的字典
        
    Returns:
        增强后的源字典
    """
    enhanced_sources = {}
    for source_id, source in sources.items():
        enhanced_sources[source_id] = enhance_source(source)
    
    logger.info(f"[CACHE-ENHANCER] 已增强 {len(enhanced_sources)} 个源的缓存机制")
    return enhanced_sources

def cache_enhanced(cls=None, *, debug=False):
    """
    缓存增强装饰器，可以用于类或方法
    
    Args:
        cls: 要装饰的类
        debug: 是否启用调试日志
        
    Returns:
        装饰后的类或方法
    """
    def decorator(cls_or_func):
        if inspect.isclass(cls_or_func):
            # 类装饰器：覆盖 __init__ 方法
            original_init = cls_or_func.__init__
            
            @functools.wraps(original_init)
            def enhanced_init(self, *args, **kwargs):
                # 调用原始 __init__
                original_init(self, *args, **kwargs)
                
                # 应用缓存增强
                enhance_source(self)
                
                if debug:
                    logger.debug(f"[CACHE-ENHANCER] 通过装饰器增强了 {self.source_id} 的缓存机制")
            
            cls_or_func.__init__ = enhanced_init
            return cls_or_func
        else:
            # 方法装饰器：直接装饰方法
            @functools.wraps(cls_or_func)
            async def wrapper(self, *args, **kwargs):
                # 如果源未被增强，先增强它
                if not hasattr(self, '_cache_enhanced') or not self._cache_enhanced:
                    enhance_source(self)
                
                # 调用原始方法
                result = await cls_or_func(self, *args, **kwargs)
                
                if debug:
                    logger.debug(f"[CACHE-ENHANCER] 调用了增强后的方法 {cls_or_func.__name__} 于源 {self.source_id}")
                
                return result
            
            return wrapper
    
    # 检查是否直接调用装饰器
    if cls is None:
        return decorator
    return decorator(cls)

# 单例模式：全局缓存监控器
class CacheMonitor:
    """全局缓存监控器"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = CacheMonitor()
        return cls._instance
    
    def __init__(self):
        """初始化缓存监控器"""
        if CacheMonitor._instance is not None:
            raise RuntimeError("请使用 CacheMonitor.get_instance() 获取实例")
        
        self.enhanced_sources = {}  # 源ID -> 增强后的源
        self.global_metrics = {
            "total_cache_hits": 0,
            "total_cache_misses": 0,
            "total_empty_protections": 0,
            "total_error_protections": 0,
            "total_shrink_protections": 0,
            "last_update_time": 0
        }
    
    def register_source(self, source: NewsSource) -> NewsSource:
        """
        注册并增强新闻源
        
        Args:
            source: 要注册的新闻源
            
        Returns:
            增强后的新闻源
        """
        # 检查源是否已被增强
        if hasattr(source, '_cache_enhanced') and source._cache_enhanced:
            self.enhanced_sources[source.source_id] = source
            return source
        
        # 增强源
        enhanced_source = enhance_source(source)
        self.enhanced_sources[source.source_id] = enhanced_source
        return enhanced_source
    
    def update_global_metrics(self) -> None:
        """更新全局指标"""
        total_hits = 0
        total_misses = 0
        total_empty_protections = 0
        total_error_protections = 0
        total_shrink_protections = 0
        
        for source_id, source in self.enhanced_sources.items():
            metrics = source._cache_metrics
            protection_stats = source._cache_protection_stats
            
            total_hits += metrics.cache_hit_count
            total_misses += metrics.cache_miss_count
            total_empty_protections += protection_stats.empty_protection_count
            total_error_protections += protection_stats.error_protection_count
            total_shrink_protections += protection_stats.shrink_protection_count
        
        self.global_metrics.update({
            "total_cache_hits": total_hits,
            "total_cache_misses": total_misses,
            "total_empty_protections": total_empty_protections,
            "total_error_protections": total_error_protections,
            "total_shrink_protections": total_shrink_protections,
            "last_update_time": time.time()
        })
    
    def get_global_status(self) -> Dict[str, Any]:
        """
        获取全局缓存状态
        
        Returns:
            全局缓存状态信息
        """
        self.update_global_metrics()
        
        total_requests = (
            self.global_metrics["total_cache_hits"] + 
            self.global_metrics["total_cache_misses"]
        )
        
        hit_ratio = (
            self.global_metrics["total_cache_hits"] / max(1, total_requests)
        )
        
        total_protections = (
            self.global_metrics["total_empty_protections"] +
            self.global_metrics["total_error_protections"] +
            self.global_metrics["total_shrink_protections"]
        )
        
        status = {
            "global_metrics": {
                "total_cache_hits": self.global_metrics["total_cache_hits"],
                "total_cache_misses": self.global_metrics["total_cache_misses"],
                "total_requests": total_requests,
                "global_hit_ratio": hit_ratio,
                "total_protections": total_protections,
                "protection_breakdown": {
                    "empty_protections": self.global_metrics["total_empty_protections"],
                    "error_protections": self.global_metrics["total_error_protections"],
                    "shrink_protections": self.global_metrics["total_shrink_protections"]
                }
            },
            "sources": {}
        }
        
        # 添加各源的状态信息
        for source_id, source in self.enhanced_sources.items():
            if hasattr(source, 'cache_status') and callable(source.cache_status):
                status["sources"][source_id] = source.cache_status()
        
        return status

# 便捷访问全局监控器
cache_monitor = CacheMonitor.get_instance()

# 便捷函数：增强一组源
def enhance_all_sources(provider):
    """
    增强提供者中的所有新闻源
    
    Args:
        provider: 新闻源提供者实例
        
    Returns:
        增强后的提供者
    """
    # 获取所有源
    sources = provider.get_all_sources()
    
    # 增强每个源
    if isinstance(sources, dict):
        # 如果是字典，直接迭代
        for source_id, source in sources.items():
            cache_monitor.register_source(source)
    else:
        # 如果是列表，迭代列表元素
        for source in sources:
            cache_monitor.register_source(source)
    
    logger.info(f"[CACHE-ENHANCER] 已增强提供者中的 {len(sources)} 个源")
    return provider 