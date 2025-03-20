"""
自动修复模块

该模块在导入时自动应用所有事件循环和HTTP客户端修复
"""

import logging
import importlib
import sys

logger = logging.getLogger(__name__)

def import_and_apply_fixes():
    """
    导入各种修复模块并应用所有修复
    """
    fixes_applied = {}
    
    # 尝试导入事件循环修复
    try:
        # 尝试不同的导入路径
        asyncio_fix = None
        for import_path in [
            "worker.asyncio_fix",
            "backend.worker.asyncio_fix",
            ".asyncio_fix"
        ]:
            try:
                asyncio_fix = importlib.import_module(import_path)
                logger.info(f"成功从 {import_path} 导入 asyncio_fix 模块")
                fixes_applied["asyncio_fix"] = True
                break
            except ImportError:
                continue
        
        if asyncio_fix is None:
            logger.warning("无法导入 asyncio_fix 模块")
            fixes_applied["asyncio_fix"] = False
    except Exception as e:
        logger.error(f"导入 asyncio_fix 模块时出错: {str(e)}")
        fixes_applied["asyncio_fix"] = False
    
    # 尝试导入HTTP客户端修复
    try:
        # 尝试不同的导入路径
        cache_fix = None
        for import_path in [
            "worker.utils.cache_fix",
            "backend.worker.utils.cache_fix",
            ".utils.cache_fix"
        ]:
            try:
                cache_fix = importlib.import_module(import_path)
                logger.info(f"成功从 {import_path} 导入 cache_fix 模块")
                fixes_applied["cache_fix"] = True
                break
            except ImportError:
                continue
        
        if cache_fix is None:
            logger.warning("无法导入 cache_fix 模块")
            fixes_applied["cache_fix"] = False
    except Exception as e:
        logger.error(f"导入 cache_fix 模块时出错: {str(e)}")
        fixes_applied["cache_fix"] = False
    
    # 返回应用的修复
    return fixes_applied

# 在导入时自动应用修复
applied_fixes = import_and_apply_fixes()

# 导出应用的修复信息，可供其他模块查询
fixes_applied = applied_fixes

def get_fixes_status():
    """获取已应用的修复状态"""
    return fixes_applied

def check_all_fixes_applied():
    """检查是否所有修复都已应用"""
    return all(fixes_applied.values()) if fixes_applied else False 