"""
aiocache 和 Redis 事件循环修复

该模块提供了修复 aiocache 和 Redis 连接中事件循环问题的功能
"""

import asyncio
import logging
import functools
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

# 类型变量用于泛型装饰器
F = TypeVar('F', bound=Callable[..., Any])

def fix_aiocache_redis_connections():
    """
    修复 aiocache 和 Redis 连接的事件循环问题
    
    这个函数会猴子补丁方式替换一些关键方法，使它们在事件循环关闭或不匹配时更加健壮
    """
    try:
        # 修复 redis.asyncio.connection.Connection
        from redis.asyncio.connection import Connection
        
        # 保存原始方法
        original_read_response = Connection.read_response
        original_connect = Connection.connect
        
        # 创建健壮的替代方法
        @functools.wraps(original_read_response)
        async def safe_read_response(self, *args, **kwargs):
            try:
                return await original_read_response(self, *args, **kwargs)
            except RuntimeError as e:
                error_msg = str(e)
                if "Event loop is closed" in error_msg or "different loop" in error_msg or "got Future" in error_msg:
                    logger.warning(f"Redis连接操作出错：{error_msg}，尝试断开连接")
                    # 确保连接关闭
                    try:
                        await self.disconnect(nowait=True)
                    except Exception:
                        pass
                    # 重新抛出一个更具体的异常，而不是通用的RuntimeError
                    raise ConnectionError(f"Redis连接问题: {error_msg}")
                else:
                    raise
        
        # 创建健壮的连接方法
        @functools.wraps(original_connect)
        async def safe_connect(self):
            try:
                return await original_connect(self)
            except RuntimeError as e:
                error_msg = str(e)
                if "Event loop is closed" in error_msg or "different loop" in error_msg or "Session and connector" in error_msg:
                    logger.warning(f"Redis连接创建出错：{error_msg}")
                    # 确保连接关闭
                    try:
                        await self.disconnect(nowait=True)
                    except Exception:
                        pass
                    # 重新抛出一个更具体的异常
                    raise ConnectionError(f"Redis连接创建问题: {error_msg}")
                else:
                    raise
        
        # 替换方法
        Connection.read_response = safe_read_response
        Connection.connect = safe_connect
        logger.info("已修复 Redis Connection 连接和响应读取方法")
        
        # 修复 redis.asyncio.client.Redis
        try:
            from redis.asyncio.client import Redis
            
            # 保存原始方法
            original_execute_command = Redis.execute_command
            
            # 创建健壮的替代方法
            @functools.wraps(original_execute_command)
            async def safe_execute_command(self, *args, **options):
                try:
                    return await original_execute_command(self, *args, **options)
                except (RuntimeError, ConnectionError) as e:
                    error_msg = str(e)
                    if "Event loop is closed" in error_msg or "different loop" in error_msg:
                        logger.warning(f"Redis执行命令出错：{error_msg}")
                        # 尝试重新连接并执行
                        try:
                            # 断开连接
                            pool = getattr(self, 'connection_pool', None)
                            if pool:
                                await pool.disconnect(inuse_connections=True)
                            
                            # 重新尝试执行命令
                            return await original_execute_command(self, *args, **options)
                        except Exception as e2:
                            logger.error(f"Redis重新连接并执行命令失败: {str(e2)}")
                            raise ConnectionError(f"Redis执行命令问题: {error_msg}")
                    else:
                        raise
            
            # 替换方法
            Redis.execute_command = safe_execute_command
            logger.info("已修复 Redis 客户端执行命令方法")
        except ImportError:
            logger.warning("无法加载 redis.asyncio.client.Redis，跳过相关修复")
        
        # 修复 aiocache.backends.redis.RedisBackend
        from aiocache.backends.redis import RedisBackend
        
        # 保存原始方法
        original_get = RedisBackend._get
        original_set = RedisBackend._set
        original_raw = RedisBackend._raw
        
        # 创建健壮的替代方法
        @functools.wraps(original_get)
        async def safe_get(self, key, encoding=None, _conn=None):
            try:
                return await original_get(self, key, encoding, _conn)
            except Exception as e:
                error_msg = str(e)
                if "Event loop is closed" in error_msg or "different loop" in error_msg or "Redis连接问题" in error_msg or "got Future" in error_msg:
                    logger.warning(f"Redis缓存获取出错：{error_msg}，返回None")
                    # 对于事件循环问题，我们直接返回None（相当于缓存未命中）
                    return None
                else:
                    logger.error(f"Couldn't retrieve http_cache:{key}:{_conn}, unexpected error")
                    logger.exception(e)
                    return None
        
        @functools.wraps(original_set)
        async def safe_set(self, key, value, ttl=None, _conn=None, _cas_token=None):
            try:
                return await original_set(self, key, value, ttl, _conn, _cas_token)
            except Exception as e:
                error_msg = str(e)
                if "Event loop is closed" in error_msg or "different loop" in error_msg or "Redis连接问题" in error_msg:
                    logger.warning(f"Redis缓存设置出错：{error_msg}，跳过缓存设置")
                    # 对于事件循环问题，我们直接返回False（相当于缓存设置失败但不影响程序运行）
                    return False
                else:
                    logger.error(f"Couldn't set http_cache:{key}, unexpected error")
                    logger.exception(e)
                    return False
        
        @functools.wraps(original_raw)
        async def safe_raw(self, command, *args, _conn=None, **kwargs):
            try:
                return await original_raw(self, command, *args, _conn=_conn, **kwargs)
            except Exception as e:
                error_msg = str(e)
                if "Event loop is closed" in error_msg or "different loop" in error_msg or "Redis连接问题" in error_msg:
                    logger.warning(f"Redis缓存原始命令出错：{error_msg}，返回None")
                    return None
                else:
                    logger.error(f"Couldn't execute raw command {command}, unexpected error")
                    logger.exception(e)
                    return None
        
        # 替换方法
        RedisBackend._get = safe_get
        RedisBackend._set = safe_set
        RedisBackend._raw = safe_raw
        logger.info("已修复 aiocache.backends.redis.RedisBackend 方法")
        
        # 完成所有修复
        logger.info("Redis 和 aiocache 事件循环修复已成功应用 ✅")
        return True
    except ImportError as e:
        logger.warning(f"无法加载所需模块进行缓存修复: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"应用缓存修复时出错: {str(e)}")
        return False

def safe_cache_decorator(cache_decorator):
    """
    使缓存装饰器更健壮的装饰器工厂
    
    Args:
        cache_decorator: 原始缓存装饰器（如aiocache.cached）
        
    Returns:
        更健壮的缓存装饰器，在事件循环问题时会退化为无缓存操作
    """
    def wrapper(*dec_args, **dec_kwargs):
        original_decorator = cache_decorator(*dec_args, **dec_kwargs)
        
        def inner_wrapper(func):
            # 记录函数名用于日志记录
            func_name = func.__name__
            
            @functools.wraps(func)
            async def wrapped_func(*args, **kwargs):
                try:
                    # 尝试使用缓存
                    decorated_func = original_decorator(func)
                    return await decorated_func(*args, **kwargs)
                except Exception as e:
                    error_msg = str(e)
                    # 如果出现事件循环或连接问题，跳过缓存直接调用函数
                    if ("Event loop is closed" in error_msg or 
                        "different loop" in error_msg or 
                        "Session and connector" in error_msg or
                        "Redis连接问题" in error_msg or
                        "got Future" in error_msg):
                        logger.warning(f"缓存操作出错，跳过缓存直接调用函数 {func_name}: {error_msg}")
                        # 直接调用原始函数
                        return await func(*args, **kwargs)
                    # 对于其它类型的错误，重新抛出
                    logger.error(f"缓存装饰器发生未处理错误: {error_msg}")
                    raise
            
            return wrapped_func
        
        return inner_wrapper
    
    return wrapper

# 应用修复
fix_aiocache_redis_connections() 