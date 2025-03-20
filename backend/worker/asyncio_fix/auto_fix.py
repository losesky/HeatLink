"""
异步事件循环自动修复

该模块提供了一个更健壮的事件循环管理系统，
解决Celery任务中的"Event loop is closed"错误。
"""

import asyncio
import functools
import logging
import sys
import threading
from typing import Any, Callable, TypeVar, cast, Optional

logger = logging.getLogger(__name__)

# 线程本地存储，用于存储每个线程的事件循环
_thread_local = threading.local()

# 类型变量，用于泛型函数签名
T = TypeVar('T')


def get_or_create_eventloop():
    """获取当前事件循环或创建新的事件循环"""
    try:
        return asyncio.get_event_loop()
    except RuntimeError as ex:
        if "There is no current event loop in thread" in str(ex):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop
        raise


def run_async(coro):
    """
    安全地运行异步协程，确保事件循环的正确创建和清理
    
    这是对asyncio.run的包装，添加了额外的错误处理和资源清理
    """
    loop = get_or_create_eventloop()
    
    # 存储在线程本地存储中
    if not hasattr(_thread_local, 'loop') or _thread_local.loop is None:
        _thread_local.loop = loop
    
    try:
        return loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"Error running async coroutine: {str(e)}")
        raise
    finally:
        # 我们不关闭事件循环，而是保持它活着
        # 这样可以避免"Event loop is closed"错误
        pass


def create_async_task_wrapper(func: Callable) -> Callable:
    """
    创建一个包装函数，该函数可以安全地运行异步任务
    
    Args:
        func: 需要包装的函数
        
    Returns:
        包装后的函数
    """
    # 保存原始属性
    original_attrs = {
        name: getattr(func, name)
        for name in dir(func)
        if not name.startswith('__') and not callable(getattr(func, name))
    }
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            # 对于异步函数，使用run_async运行
            if asyncio.iscoroutinefunction(func):
                return run_async(func(*args, **kwargs))
            
            # 对于同步函数，直接运行
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in async task wrapper: {str(e)}")
            # 重新抛出异常，让Celery处理
            raise
    
    # 复制原始属性
    for name, value in original_attrs.items():
        setattr(wrapper, name, value)
    
    # 对于Celery任务，特别处理delay和apply_async方法
    if hasattr(func, 'delay'):
        wrapper.delay = func.delay
    if hasattr(func, 'apply_async'):
        wrapper.apply_async = func.apply_async
    
    return wrapper


def ensure_event_loop_safety(tasks_module):
    """
    确保指定模块中的所有任务都使用安全的事件循环管理
    
    Args:
        tasks_module: 包含Celery任务的模块
    """
    # 定义需要修复的任务函数名
    tasks_to_fix = [
        'schedule_source_updates',
        'fetch_high_frequency_sources',
        'fetch_medium_frequency_sources',
        'fetch_low_frequency_sources',
        'fetch_all_news',
        'fetch_source_news'
    ]
    
    # 修复辅助异步函数
    logger.info("正在修复异步辅助函数...")
    if hasattr(tasks_module, '_fetch_source_news'):
        original_fetch_source_news = tasks_module._fetch_source_news
        
        @functools.wraps(original_fetch_source_news)
        async def safe_fetch_source_news(*args, **kwargs):
            try:
                return await original_fetch_source_news(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in _fetch_source_news: {str(e)}")
                raise
        
        tasks_module._fetch_source_news = safe_fetch_source_news
        logger.info("已修复 news._fetch_source_news 函数")
    
    if hasattr(tasks_module, '_fetch_sources_news'):
        original_fetch_sources_news = tasks_module._fetch_sources_news
        
        @functools.wraps(original_fetch_sources_news)
        async def safe_fetch_sources_news(*args, **kwargs):
            try:
                return await original_fetch_sources_news(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in _fetch_sources_news: {str(e)}")
                raise
        
        tasks_module._fetch_sources_news = safe_fetch_sources_news
        logger.info("已修复 news._fetch_sources_news 函数")
    
    # 为每个函数名获取对应的任务实例
    task_instances = {}
    for task_name in tasks_to_fix:
        task_full_name = f"news.{task_name}"
        original_task = getattr(tasks_module, task_name, None)
        if original_task is None:
            continue
        task_instances[task_name] = original_task
    
    # 修复Celery任务
    for task_name, original_task in task_instances.items():
        task_full_name = f"news.{task_name}"
        
        # 创建安全的任务包装
        safe_task = create_async_task_wrapper(original_task)
        
        # 替换原始任务
        setattr(tasks_module, task_name, safe_task)
        logger.info(f"已修复 {task_full_name} 任务")
    
    logger.info("所有Celery任务异步循环问题修复已完成")


def fix_aiohttp_session():
    """
    修复aiohttp ClientSession的关闭问题
    
    为ClientSession添加更安全的关闭方法，避免'Event loop is closed'错误
    """
    try:
        import aiohttp
        logger.info("准备修复HTTP客户端...")
        
        # 保存原始的关闭方法
        original_close = aiohttp.ClientSession.close
        
        @functools.wraps(original_close)
        async def safe_close(self):
            try:
                await original_close(self)
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    logger.debug("忽略ClientSession关闭时的'Event loop is closed'错误")
                else:
                    raise
        
        # 替换关闭方法
        aiohttp.ClientSession.close = safe_close
        logger.info("已修复aiohttp.ClientSession.close方法")
        
    except (ImportError, AttributeError) as e:
        logger.warning(f"无法修复HTTP客户端: {str(e)}")
    except Exception as e:
        logger.error(f"修复HTTP客户端时发生错误: {str(e)}")


def apply_all_fixes():
    """应用所有的修复"""
    try:
        # 修复aiohttp会话
        fix_aiohttp_session()
        
        # 导入任务模块
        try:
            from worker.tasks import news as news_tasks
            ensure_event_loop_safety(news_tasks)
        except ImportError:
            try:
                from backend.worker.tasks import news as news_tasks
                ensure_event_loop_safety(news_tasks)
            except ImportError:
                logger.warning("无法导入news任务模块")
        
        logger.info("所有修复已成功应用")
    except Exception as e:
        logger.error(f"应用修复时发生错误: {str(e)}") 