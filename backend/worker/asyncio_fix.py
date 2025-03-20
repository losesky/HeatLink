"""
事件循环和异步任务修复模块

该模块提供了解决多线程环境下的事件循环问题的工具和修复方法
"""

import asyncio
import functools
import inspect
import logging
import threading
import weakref
from typing import Any, Callable, Dict, Optional, TypeVar, Union, List, Set

logger = logging.getLogger(__name__)

# 线程本地存储
_thread_local = threading.local()

# 全局事件循环缓存，用于跟踪所有创建的事件循环
# 使用弱引用字典以避免内存泄漏
_loop_registry = weakref.WeakValueDictionary()
_registry_lock = threading.RLock()

def get_or_create_eventloop() -> asyncio.AbstractEventLoop:
    """
    获取当前线程的事件循环，如果不存在则创建一个新的
    
    确保每个线程只有一个事件循环，并且该循环在线程存活期间保持有效
    
    Returns:
        当前线程的事件循环
    """
    # 获取当前线程ID
    thread_id = threading.get_ident()
    
    # 首先检查线程本地存储
    if hasattr(_thread_local, 'loop') and _thread_local.loop is not None:
        loop = _thread_local.loop
        # 确保事件循环仍然有效
        if not loop.is_closed():
            return loop
    
    # 如果线程本地存储中没有或者已关闭，尝试从注册表中获取
    with _registry_lock:
        if thread_id in _loop_registry:
            loop = _loop_registry[thread_id]
            if not loop.is_closed():
                _thread_local.loop = loop
                return loop
    
    # 创建一个新的事件循环
    try:
        # 先尝试获取当前事件循环
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # 如果获取失败，创建一个新的
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # 保存到线程本地存储和全局注册表
    _thread_local.loop = loop
    with _registry_lock:
        _loop_registry[thread_id] = loop
    
    logger.debug(f"为线程 {thread_id} 创建/获取了新的事件循环，ID: {id(loop)}")
    return loop

# 类型变量，用于保持装饰器的类型提示
F = TypeVar('F', bound=Callable[..., Any])

def ensure_event_loop(func: F) -> F:
    """
    装饰器：确保异步函数在有效的事件循环中执行
    
    如果事件循环不存在或已关闭，将创建一个新的
    
    Args:
        func: 要装饰的异步函数
        
    Returns:
        装饰后的函数
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # 确保事件循环有效
        get_or_create_eventloop()
        try:
            return await func(*args, **kwargs)
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                logger.warning(f"检测到事件循环已关闭，为函数 {func.__name__} 创建新循环")
                # 创建新循环并重试
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                _thread_local.loop = loop
                thread_id = threading.get_ident()
                with _registry_lock:
                    _loop_registry[thread_id] = loop
                # 重试
                return await func(*args, **kwargs)
            raise
    
    # 如果原函数不是协程函数，返回原始函数
    if not inspect.iscoroutinefunction(func):
        return func
    
    return wrapper

def run_async(coro, timeout=None):
    """
    在当前线程的事件循环中运行协程，如果事件循环不存在或已关闭，则创建一个新的
    
    Args:
        coro: 要运行的协程
        timeout: 超时时间，如果提供则使用wait_for包装协程
        
    Returns:
        协程的执行结果
    """
    loop = get_or_create_eventloop()
    
    if timeout is not None:
        coro = asyncio.wait_for(coro, timeout)
    
    try:
        if loop.is_running():
            # 如果循环正在运行，创建一个future并运行
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result()
        else:
            # 如果循环未运行，直接运行
            return loop.run_until_complete(coro)
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            # 创建新循环并重试
            logger.warning("检测到事件循环已关闭，创建新循环")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _thread_local.loop = loop
            thread_id = threading.get_ident()
            with _registry_lock:
                _loop_registry[thread_id] = loop
            # 重试
            return loop.run_until_complete(coro)
        raise

def fix_aiohttp_session_close():
    """
    修复aiohttp的ClientSession.close方法
    
    该方法在事件循环关闭时可能会引发RuntimeError
    """
    try:
        from aiohttp import ClientSession
        original_close = ClientSession.close
        
        @functools.wraps(original_close)
        async def safe_close(self):
            try:
                return await original_close(self)
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    logger.warning("忽略ClientSession.close中的'Event loop is closed'错误")
                    return None
                raise
        
        # 替换方法
        ClientSession.close = safe_close
        logger.info("已修复aiohttp.ClientSession.close方法")
        
        return True
    except ImportError:
        logger.warning("无法导入aiohttp，跳过ClientSession.close修复")
        return False
    except Exception as e:
        logger.error(f"修复aiohttp.ClientSession.close出错: {str(e)}")
        return False

def fix_asyncio_gather():
    """
    修复asyncio.gather函数，使其在事件循环关闭或任务已取消时更加健壮
    """
    try:
        original_gather = asyncio.gather
        
        @functools.wraps(original_gather)
        async def safe_gather(*coros_or_futures, **kwargs):
            try:
                return await original_gather(*coros_or_futures, **kwargs)
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    logger.warning("asyncio.gather检测到事件循环关闭，返回None")
                    return None
                raise
            except asyncio.CancelledError:
                logger.warning("asyncio.gather任务被取消")
                return None
        
        # 替换函数
        asyncio.gather = safe_gather
        logger.info("已修复asyncio.gather函数")
        
        return True
    except Exception as e:
        logger.error(f"修复asyncio.gather出错: {str(e)}")
        return False

def fix_celery_tasks():
    """
    修复Celery任务的异步方法，使其可以正确处理事件循环
    """
    try:
        from celery import Task
        from celery.app.task import Context
        
        # 创建一个任务调用的上下文管理器
        class CeleryAsyncContext:
            def __init__(self, task):
                self.task = task
                self.original_loop = None
                
            def __enter__(self):
                # 确保线程有一个工作的事件循环
                self.original_loop = asyncio.get_event_loop_policy().get_event_loop()
                if self.original_loop.is_closed():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    _thread_local.loop = new_loop
                    thread_id = threading.get_ident()
                    with _registry_lock:
                        _loop_registry[thread_id] = new_loop
                return self.task
                
            def __exit__(self, exc_type, exc_val, exc_tb):
                # 恢复原来的事件循环
                if self.original_loop and not self.original_loop.is_closed():
                    asyncio.set_event_loop(self.original_loop)
                return False
        
        # 修改Task的__call__方法，确保它有一个有效的事件循环
        original_call = Task.__call__
        
        @functools.wraps(original_call)
        def safe_call(self, *args, **kwargs):
            with CeleryAsyncContext(self):
                return original_call(self, *args, **kwargs)
        
        # 修改delay和apply_async方法，确保它们能正确序列化参数
        original_delay = Task.delay
        original_apply_async = Task.apply_async
        
        @functools.wraps(original_delay)
        def safe_delay(self, *args, **kwargs):
            # 处理不可序列化的参数
            clean_args = []
            for arg in args:
                if isinstance(arg, (set, frozenset)):
                    clean_args.append(list(arg))
                else:
                    clean_args.append(arg)
            
            clean_kwargs = {}
            for k, v in kwargs.items():
                if isinstance(v, (set, frozenset)):
                    clean_kwargs[k] = list(v)
                else:
                    clean_kwargs[k] = v
            
            return original_delay(self, *clean_args, **clean_kwargs)
        
        @functools.wraps(original_apply_async)
        def safe_apply_async(self, args=None, kwargs=None, **options):
            # 处理不可序列化的参数
            clean_args = []
            if args:
                for arg in args:
                    if isinstance(arg, (set, frozenset)):
                        clean_args.append(list(arg))
                    else:
                        clean_args.append(arg)
            
            clean_kwargs = {}
            if kwargs:
                for k, v in kwargs.items():
                    if isinstance(v, (set, frozenset)):
                        clean_kwargs[k] = list(v)
                    else:
                        clean_kwargs[k] = v
            
            return original_apply_async(self, args=clean_args or None, kwargs=clean_kwargs or None, **options)
        
        # 替换方法
        Task.__call__ = safe_call
        Task.delay = safe_delay
        Task.apply_async = safe_apply_async
        
        logger.info("已修复Celery任务方法")
        return True
    except ImportError:
        logger.warning("无法导入Celery，跳过任务修复")
        return False
    except Exception as e:
        logger.error(f"修复Celery任务出错: {str(e)}")
        return False

def apply_all_fixes():
    """应用所有修复"""
    fixes = [
        fix_aiohttp_session_close,
        fix_asyncio_gather,
        fix_celery_tasks
    ]
    
    results = {}
    for fix in fixes:
        try:
            name = fix.__name__
            result = fix()
            results[name] = result
            logger.info(f"应用修复 {name}: {'成功' if result else '失败'}")
        except Exception as e:
            results[fix.__name__] = False
            logger.error(f"应用修复 {fix.__name__} 时出错: {str(e)}")
    
    return results

# 自动应用所有修复
apply_all_fixes() 