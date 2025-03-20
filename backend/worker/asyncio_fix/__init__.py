"""
异步事件循环修复模块

该包提供了一系列工具和修复，用于解决Celery任务中的异步事件循环问题。
"""

import sys
import os

# 添加当前目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 从auto_fix模块导入函数
try:
    from worker.asyncio_fix.auto_fix import apply_all_fixes, get_or_create_eventloop, run_async
except ImportError:
    try:
        from backend.worker.asyncio_fix.auto_fix import apply_all_fixes, get_or_create_eventloop, run_async
    except ImportError:
        # 定义空函数，避免导入错误
        def apply_all_fixes(): pass
        def get_or_create_eventloop(): pass
        def run_async(coro): return None

__all__ = ['apply_all_fixes', 'get_or_create_eventloop', 'run_async']
