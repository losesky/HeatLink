from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from typing import List, Dict, Any, Optional
import asyncio
import sys
import os
from pathlib import Path
import logging

# 添加backend目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from worker.cache import CacheManager
from app.core.config import settings
from app.api import deps

# Redis缓存前缀常量
SOURCE_CACHE_PREFIX = "source:"

router = APIRouter()

# 创建全局缓存管理器
cache_manager = None

async def get_cache_manager():
    """获取或初始化缓存管理器"""
    global cache_manager
    if cache_manager is None:
        cache_manager = CacheManager(
            redis_url=settings.REDIS_URL,
            enable_memory_cache=True,
            verbose_logging=True
        )
        await cache_manager.initialize()
    return cache_manager


@router.get("/stats", response_model=Dict[str, Any])
async def get_cache_stats(
    pattern: str = Query(f"{SOURCE_CACHE_PREFIX}*", description="缓存键匹配模式")
):
    """
    获取Redis缓存统计信息
    """
    try:
        cm = await get_cache_manager()
        
        # 获取匹配的缓存键
        keys = []
        if cm.redis:
            keys = await cm.redis.keys(pattern)
        
        total_items = 0
        ttl_values = []
        source_stats = []
        no_cache_sources = []
        
        # 获取所有已知的源ID列表
        from worker.sources.provider import DefaultNewsSourceProvider
        provider = DefaultNewsSourceProvider()
        all_sources = provider.get_all_sources()
        all_source_ids = [source.source_id for source in all_sources]
        
        # 检查每个源的缓存状态
        for source_id in all_source_ids:
            cache_key = f"{SOURCE_CACHE_PREFIX}{source_id}"
            if cache_key.encode() in keys or cache_key in keys:  # 兼容字节和字符串键
                # 获取该源的缓存数据
                cached_data = await cm.get(cache_key)
                items_count = len(cached_data) if isinstance(cached_data, list) else 0
                total_items += items_count
                
                # 获取TTL
                ttl = -1
                if cm.redis:
                    ttl = await cm.redis.ttl(cache_key)
                    if ttl > 0:
                        ttl_values.append(ttl)
                
                # 获取内存使用情况
                memory_usage = "未知"
                if cm.redis:
                    try:
                        memory_info = await cm.redis.memory_usage(cache_key)
                        if memory_info:
                            memory_usage = _format_size(memory_info)
                    except:
                        pass
                
                # 添加源缓存统计
                source_stats.append({
                    "id": source_id,
                    "name": next((s.name for s in all_sources if s.source_id == source_id), source_id),
                    "has_cache": True,
                    "items_count": items_count,
                    "ttl": ttl,
                    "memory": memory_usage,
                    "cache_key": cache_key
                })
            else:
                # 添加到无缓存源列表
                source_name = next((s.name for s in all_sources if s.source_id == source_id), source_id)
                no_cache_sources.append(source_id)
                source_stats.append({
                    "id": source_id,
                    "name": source_name,
                    "has_cache": False,
                    "items_count": 0,
                    "ttl": -1,
                    "memory": "0B",
                    "cache_key": cache_key
                })
        
        # 计算平均TTL
        avg_ttl = sum(ttl_values) / len(ttl_values) if ttl_values else 0
        
        # 获取Redis内存使用情况
        memory_usage = "未知"
        if cm.redis:
            try:
                info = await cm.redis.info("memory")
                if info and "used_memory_human" in info:
                    memory_usage = info["used_memory_human"]
            except:
                pass
        
        return {
            "total_keys": len(keys),
            "total_items": total_items,
            "average_ttl": avg_ttl,
            "memory_usage": memory_usage,
            "no_cache_sources": no_cache_sources,
            "sources": sorted(source_stats, key=lambda x: x["id"])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取缓存统计失败: {str(e)}")


@router.post("/refresh", response_model=Dict[str, Any])
async def refresh_cache(
    sources: Optional[List[str]] = Query(None, description="要刷新的源ID列表，不提供则刷新所有源"),
    background_tasks: BackgroundTasks = None
):
    """
    刷新Redis缓存
    """
    try:
        # 获取缓存管理器
        cm = await get_cache_manager()
        
        # 导入调度器
        from worker.scheduler import AdaptiveScheduler
        from worker.sources.provider import DefaultNewsSourceProvider
        
        # 创建源提供者
        provider = DefaultNewsSourceProvider()
        
        # 创建调度器
        scheduler = AdaptiveScheduler(
            source_provider=provider,
            cache_manager=cm,
            enable_adaptive=False
        )
        
        # 初始化调度器
        await scheduler.initialize()
        
        # 获取要刷新的源列表 - 修复URL参数处理
        if not sources:
            all_sources = scheduler.get_all_sources()
            sources = [source.source_id for source in all_sources]
        
        # 结果字典
        results = {}
        
        # 异步刷新函数
        async def async_refresh_sources():
            for source_id in sources:
                try:
                    # 强制刷新
                    success = await scheduler.fetch_source(source_id, force=True)
                    results[source_id] = success
                except Exception as e:
                    results[source_id] = False
            
            # 移除对不存在的close方法的调用
            # 注释掉以下行:
            # await scheduler.close()
        
        # 在后台刷新或立即刷新
        if background_tasks:
            background_tasks.add_task(async_refresh_sources)
            message = f"已开始刷新 {len(sources)} 个源的缓存"
            status = "processing"
        else:
            await async_refresh_sources()
            success_count = sum(1 for result in results.values() if result)
            message = f"已完成刷新 {success_count}/{len(sources)} 个源的缓存"
            status = "completed"
        
        return {
            "status": status,
            "message": message,
            "sources": sources,
            "results": results if status == "completed" else {}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"刷新缓存失败: {str(e)}")


@router.delete("/clear", response_model=Dict[str, Any])
async def clear_cache(
    pattern: str = Query(f"{SOURCE_CACHE_PREFIX}*", description="要清除的缓存键匹配模式"),
    force: bool = Query(False, description="是否强制清除，不再提示确认")
):
    """
    清除Redis缓存
    """
    try:
        # 获取缓存管理器
        cm = await get_cache_manager()
        
        # 获取匹配的键
        keys = []
        if cm.redis:
            keys = await cm.redis.keys(pattern)
        
        if not keys:
            return {"success": True, "message": "未找到匹配的缓存键", "deleted_count": 0}
        
        # 删除键
        await cm.clear(pattern)
        
        return {
            "success": True,
            "message": f"已清除 {len(keys)} 个缓存键",
            "deleted_count": len(keys),
            "pattern": pattern
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清除缓存失败: {str(e)}")


@router.get("/keys", response_model=Dict[str, Any])
async def list_cache_keys(
    pattern: str = Query(f"{SOURCE_CACHE_PREFIX}*", description="缓存键匹配模式")
):
    """
    列出Redis缓存键
    """
    try:
        # 获取缓存管理器
        cm = await get_cache_manager()
        
        # 获取匹配的键
        keys = []
        if cm.redis:
            keys = await cm.redis.keys(pattern)
        
        return {
            "count": len(keys),
            "pattern": pattern,
            "keys": sorted(keys)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"列出缓存键失败: {str(e)}")


@router.get("/source/{source_id}", response_model=Dict[str, Any])
async def get_source_cache(
    source_id: str
):
    """
    获取特定源的缓存数据
    """
    try:
        # 获取缓存管理器
        cm = await get_cache_manager()
        
        # 构建缓存键
        cache_key = f"{SOURCE_CACHE_PREFIX}{source_id}"
        
        # 获取缓存数据
        cached_data = await cm.get(cache_key)
        
        # 获取TTL
        ttl = -1
        if cm.redis:
            ttl = await cm.redis.ttl(cache_key)
        
        # 获取内存使用情况
        memory_usage = "未知"
        if cm.redis:
            try:
                memory_info = await cm.redis.memory_usage(cache_key)
                if memory_info:
                    memory_usage = _format_size(memory_info)
            except:
                pass
        
        # 处理缓存数据
        items = []
        if cached_data and isinstance(cached_data, list):
            for item in cached_data:
                try:
                    if hasattr(item, 'dict') and callable(getattr(item, 'dict')):
                        # Pydantic模型或类似具有dict()方法的对象
                        item_dict = item.dict()
                        # 处理日期时间对象
                        for k, v in item_dict.items():
                            if hasattr(v, 'isoformat'):  # 如日期时间对象
                                item_dict[k] = v.isoformat()
                        items.append(item_dict)
                    elif hasattr(item, 'to_dict') and callable(getattr(item, 'to_dict')):
                        # 具有to_dict()方法的对象
                        item_dict = item.to_dict()
                        items.append(item_dict)
                    elif hasattr(item, '__dict__'):
                        # 常规Python对象，使用__dict__
                        item_dict = item.__dict__.copy()
                        # 处理日期时间对象
                        for k, v in item_dict.items():
                            if hasattr(v, 'isoformat'):  # 如日期时间对象
                                item_dict[k] = v.isoformat()
                        items.append(item_dict)
                    else:
                        # 直接添加字典对象
                        items.append(item)
                except Exception as e:
                    # 继续处理下一个项目
                    continue
        
        return {
            "source_id": source_id,
            "cache_key": cache_key,
            "ttl": ttl,
            "memory_usage": memory_usage,
            "items_count": len(items),
            "has_cache": len(items) > 0,
            "items": items
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取源缓存数据失败: {str(e)}")


@router.get("/performance", response_model=Dict[str, Any])
async def get_cache_performance():
    """
    获取Redis缓存性能指标
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        cm = await get_cache_manager()
        
        if not cm.redis:
            return {
                "success": False,
                "message": "Redis连接不可用",
                "metrics": {}
            }
            
        # 获取Redis服务器信息
        metrics = {}
        
        # 直接获取所有Redis信息
        all_info = await cm.redis.info()
        logger.debug(f"Redis info类型: {type(all_info)}")
        
        # 处理嵌套结构
        # 服务器信息
        metrics["server"] = {}
        server_data = all_info.get("server", {}) if isinstance(all_info.get("server"), dict) else all_info
        
        metrics["server"] = {
            "redis_version": server_data.get("redis_version", "未知"),
            "uptime_in_seconds": _safe_int(server_data.get("uptime_in_seconds", 0)),
            "uptime_in_days": _safe_int(server_data.get("uptime_in_days", 0)),
            "connected_clients": _safe_int(server_data.get("connected_clients", 0)),
            "blocked_clients": _safe_int(server_data.get("blocked_clients", 0))
        }
        
        # 内存信息
        memory_data = all_info.get("memory", {}) if isinstance(all_info.get("memory"), dict) else all_info
        metrics["memory"] = {
            "used_memory": _safe_int(memory_data.get("used_memory", 0)),
            "used_memory_human": memory_data.get("used_memory_human", "未知"),
            "used_memory_peak": _safe_int(memory_data.get("used_memory_peak", 0)),
            "used_memory_peak_human": memory_data.get("used_memory_peak_human", "未知"),
            "used_memory_lua": _safe_int(memory_data.get("used_memory_lua", 0)),
            "mem_fragmentation_ratio": _safe_float(memory_data.get("mem_fragmentation_ratio", 0))
        }
        
        # 确保内存使用信息显示为可读格式
        if metrics["memory"]["used_memory_human"] == "未知" and metrics["memory"]["used_memory"] > 0:
            metrics["memory"]["used_memory_human"] = _format_size(metrics["memory"]["used_memory"])
        
        if metrics["memory"]["used_memory_peak_human"] == "未知" and metrics["memory"]["used_memory_peak"] > 0:
            metrics["memory"]["used_memory_peak_human"] = _format_size(metrics["memory"]["used_memory_peak"])
        
        # 统计信息
        stats_data = all_info.get("stats", {}) if isinstance(all_info.get("stats"), dict) else all_info
        metrics["stats"] = {
            "total_connections_received": _safe_int(stats_data.get("total_connections_received", 0)),
            "total_commands_processed": _safe_int(stats_data.get("total_commands_processed", 0)),
            "instantaneous_ops_per_sec": _safe_int(stats_data.get("instantaneous_ops_per_sec", 0)),
            "rejected_connections": _safe_int(stats_data.get("rejected_connections", 0)),
            "expired_keys": _safe_int(stats_data.get("expired_keys", 0)),
            "evicted_keys": _safe_int(stats_data.get("evicted_keys", 0)),
            "keyspace_hits": _safe_int(stats_data.get("keyspace_hits", 0)),
            "keyspace_misses": _safe_int(stats_data.get("keyspace_misses", 0))
        }
        
        # 计算缓存命中率
        hits = metrics["stats"]["keyspace_hits"]
        misses = metrics["stats"]["keyspace_misses"]
        total = hits + misses
        metrics["stats"]["hit_rate"] = round(hits / total * 100, 2) if total > 0 else 0
        
        # 数据库信息
        metrics["databases"] = {}
        keyspace_data = all_info.get("keyspace", {}) if isinstance(all_info.get("keyspace"), dict) else all_info
        
        # 处理keyspace中的数据库信息
        for key, value in keyspace_data.items():
            if key.startswith("db"):
                try:
                    metrics["databases"][key] = value
                except Exception as parse_error:
                    logger.error(f"解析数据库信息出错: {parse_error}, 键={key}, 值={value}")
        
        # 如果keyspace数据不在嵌套结构中，则从顶层获取
        if not metrics["databases"]:
            for key, value in all_info.items():
                if key.startswith("db"):
                    try:
                        if isinstance(value, dict):
                            metrics["databases"][key] = value
                        elif isinstance(value, str):
                            # 解析形如 "keys=90,expires=90,avg_ttl=2383834,subexpiry=0" 的字符串
                            parts = value.split(",")
                            db_info = {}
                            for part in parts:
                                if "=" in part:
                                    k, v = part.split("=")
                                    db_info[k] = v
                            metrics["databases"][key] = db_info
                    except Exception as parse_error:
                        logger.error(f"解析数据库信息出错: {parse_error}, 键={key}, 值={value}")
        
        # 总数据库大小
        total_keys = 0
        for db_info in metrics["databases"].values():
            if isinstance(db_info, dict) and "keys" in db_info:
                try:
                    total_keys += _safe_int(db_info["keys"])
                except (ValueError, TypeError):
                    pass
        
        metrics["summary"] = {
            "total_keys": total_keys,
            "total_databases": len(metrics["databases"]),
            "memory_usage": metrics["memory"]["used_memory_human"]
        }
        
        # 获取系统时间
        import time
        metrics["timestamp"] = int(time.time())
        
        return {
            "success": True,
            "message": "成功获取Redis性能指标",
            "metrics": metrics
        }
    except Exception as e:
        logger.error(f"获取Redis性能指标失败: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"获取Redis性能指标失败: {str(e)}",
            "metrics": {}
        }

def _safe_int(value):
    """
    安全地将值转换为整数
    """
    if value is None:
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0

def _safe_float(value):
    """
    安全地将值转换为浮点数
    """
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

# 辅助函数
def _format_size(size_bytes: int) -> str:
    """将字节大小格式化为可读字符串"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f}MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f}GB" 