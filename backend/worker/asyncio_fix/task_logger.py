"""
任务日志助手

提供更详细的任务执行日志记录，以便于调试和分析异步任务问题
"""

import time
import logging
import functools
import traceback
import threading
from typing import Callable, Any, Dict, List, Optional, Set

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 线程本地存储，用于记录当前任务上下文
_task_context = threading.local()

# 全局任务注册表
_task_registry = {}
_registry_lock = threading.Lock()


def get_current_task_context() -> Dict[str, Any]:
    """获取当前任务的上下文信息"""
    if not hasattr(_task_context, 'context'):
        _task_context.context = {
            'task_id': None,
            'task_name': None,
            'start_time': None,
            'metadata': {},
            'errors': [],
            'warnings': [],
            'steps': []
        }
    return _task_context.context


def set_task_context(task_id: str, task_name: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """设置当前任务的上下文信息"""
    context = {
        'task_id': task_id,
        'task_name': task_name,
        'start_time': time.time(),
        'metadata': metadata or {},
        'errors': [],
        'warnings': [],
        'steps': []
    }
    _task_context.context = context
    
    # 注册到全局注册表
    with _registry_lock:
        _task_registry[task_id] = context
    
    return context


def add_task_error(error: str, exception: Optional[Exception] = None) -> None:
    """添加任务错误"""
    context = get_current_task_context()
    error_data = {
        'message': error,
        'timestamp': time.time(),
        'traceback': traceback.format_exc() if exception else None
    }
    context['errors'].append(error_data)
    
    # 记录到日志
    if exception:
        logger.error(f"任务错误 [{context['task_name']}]: {error}", exc_info=exception)
    else:
        logger.error(f"任务错误 [{context['task_name']}]: {error}")


def add_task_warning(warning: str) -> None:
    """添加任务警告"""
    context = get_current_task_context()
    warning_data = {
        'message': warning,
        'timestamp': time.time()
    }
    context['warnings'].append(warning_data)
    
    # 记录到日志
    logger.warning(f"任务警告 [{context['task_name']}]: {warning}")


def add_task_step(step_name: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """添加任务步骤"""
    context = get_current_task_context()
    step_data = {
        'name': step_name,
        'start_time': time.time(),
        'end_time': None,
        'duration': None,
        'status': 'running',
        'metadata': metadata or {},
        'errors': []
    }
    context['steps'].append(step_data)
    
    # 记录到日志
    logger.info(f"任务步骤开始 [{context['task_name']}]: {step_name}")
    
    return step_data


def complete_task_step(step_name: str, status: str = 'success', error: Optional[str] = None) -> None:
    """完成任务步骤"""
    context = get_current_task_context()
    
    # 查找步骤
    for step in context['steps']:
        if step['name'] == step_name and step['status'] == 'running':
            step['end_time'] = time.time()
            step['duration'] = step['end_time'] - step['start_time']
            step['status'] = status
            
            if error:
                step['errors'].append({
                    'message': error,
                    'timestamp': time.time()
                })
                logger.error(f"任务步骤错误 [{context['task_name']}][{step_name}]: {error}")
            
            # 记录到日志
            duration_ms = int(step['duration'] * 1000)
            if status == 'success':
                logger.info(f"任务步骤完成 [{context['task_name']}][{step_name}]: {duration_ms}ms")
            else:
                logger.warning(f"任务步骤{status} [{context['task_name']}][{step_name}]: {duration_ms}ms")
            
            return
    
    # 如果找不到匹配的步骤
    logger.warning(f"无法找到匹配的运行中步骤: {step_name}")


def complete_task(task_id: Optional[str] = None, status: str = 'success', result: Any = None) -> Dict[str, Any]:
    """完成任务，并返回执行统计信息"""
    if task_id:
        with _registry_lock:
            context = _task_registry.get(task_id)
    else:
        context = get_current_task_context()
    
    if not context:
        logger.warning(f"无法找到任务上下文: {task_id}")
        return {}
    
    # 计算任务执行时间
    end_time = time.time()
    duration = end_time - context['start_time']
    
    # 添加任务完成信息
    context['end_time'] = end_time
    context['duration'] = duration
    context['status'] = status
    context['result'] = result
    
    # 记录到日志
    duration_ms = int(duration * 1000)
    task_name = context['task_name']
    error_count = len(context['errors'])
    warning_count = len(context['warnings'])
    
    if status == 'success':
        if error_count > 0 or warning_count > 0:
            logger.info(f"任务完成 [{task_name}] 但有 {error_count} 个错误和 {warning_count} 个警告，耗时: {duration_ms}ms")
        else:
            logger.info(f"任务成功完成 [{task_name}]，耗时: {duration_ms}ms")
    else:
        logger.warning(f"任务{status} [{task_name}]，有 {error_count} 个错误，耗时: {duration_ms}ms")
    
    # 构建任务统计信息
    stats = {
        'task_id': context['task_id'],
        'task_name': task_name,
        'duration_ms': duration_ms,
        'status': status,
        'error_count': error_count,
        'warning_count': warning_count,
        'step_count': len(context['steps'])
    }
    
    return stats


def log_task_execution(func: Callable) -> Callable:
    """装饰器：记录任务执行情况"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # 获取任务名称
        task_name = getattr(func, '__qualname__', func.__name__)
        
        # 生成任务ID
        import uuid
        task_id = str(uuid.uuid4())
        
        # 设置任务上下文
        set_task_context(task_id, task_name, {
            'args': str(args),
            'kwargs': str(kwargs)
        })
        
        # 添加初始步骤
        add_task_step('task_start')
        
        try:
            # 执行任务
            add_task_step('task_execution')
            result = func(*args, **kwargs)
            complete_task_step('task_execution')
            
            # 完成任务
            stats = complete_task(task_id, 'success', result)
            complete_task_step('task_start')
            
            return result
        except Exception as e:
            # 记录错误
            add_task_error(f"任务执行异常: {str(e)}", e)
            complete_task_step('task_execution', 'error', str(e))
            
            # 完成任务
            stats = complete_task(task_id, 'error')
            complete_task_step('task_start', 'error')
            
            # 重新抛出异常
            raise
    
    return wrapper


def log_async_task_execution(func: Callable) -> Callable:
    """装饰器：记录异步任务执行情况"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # 获取任务名称
        task_name = getattr(func, '__qualname__', func.__name__)
        
        # 生成任务ID
        import uuid
        task_id = str(uuid.uuid4())
        
        # 设置任务上下文
        set_task_context(task_id, task_name, {
            'args': str(args),
            'kwargs': str(kwargs)
        })
        
        # 添加初始步骤
        add_task_step('task_start')
        
        try:
            # 执行任务
            add_task_step('task_execution')
            result = await func(*args, **kwargs)
            complete_task_step('task_execution')
            
            # 完成任务
            stats = complete_task(task_id, 'success', result)
            complete_task_step('task_start')
            
            return result
        except Exception as e:
            # 记录错误
            add_task_error(f"异步任务执行异常: {str(e)}", e)
            complete_task_step('task_execution', 'error', str(e))
            
            # 完成任务
            stats = complete_task(task_id, 'error')
            complete_task_step('task_start', 'error')
            
            # 重新抛出异常
            raise
    
    return wrapper 