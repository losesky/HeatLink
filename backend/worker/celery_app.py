import os
import sys
import logging
from celery import Celery

from app.core.config import settings

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 检查是否应该显示详细日志
VERBOSE_LOGGING = os.environ.get('LOG_LEVEL', 'INFO').upper() != 'ERROR'

# 确保应用事件循环修复
def ensure_asyncio_fixes():
    """确保应用所有必要的事件循环修复"""
    fixes_applied = {}
    
    try:
        # 尝试导入和应用auto_fix模块
        try:
            from backend.worker import auto_fix as asyncio_fixes
            fixes_applied["auto_fix_module"] = True
            logger.info("成功导入了 backend.worker.auto_fix 模块")
            if hasattr(asyncio_fixes, 'get_fixes_status'):
                auto_fixes = asyncio_fixes.get_fixes_status()
                for fix_name, status in auto_fixes.items():
                    fixes_applied[fix_name] = status
                    logger.info(f"修复 {fix_name}: {'已应用' if status else '未应用'}")
        except ImportError:
            try:
                from worker import auto_fix as asyncio_fixes
                fixes_applied["auto_fix_module"] = True
                logger.info("成功导入了 worker.auto_fix 模块")
                if hasattr(asyncio_fixes, 'get_fixes_status'):
                    auto_fixes = asyncio_fixes.get_fixes_status()
                    for fix_name, status in auto_fixes.items():
                        fixes_applied[fix_name] = status
                        logger.info(f"修复 {fix_name}: {'已应用' if status else '未应用'}")
            except ImportError:
                fixes_applied["auto_fix_module"] = False
                logger.warning("⚠️ 无法导入 auto_fix 模块，将尝试直接导入各个修复模块")
        
        # 显式尝试导入和应用asyncio_fix模块的修复
        try:
            import_paths = [
                "backend.worker.asyncio_fix",
                "worker.asyncio_fix"
            ]
            asyncio_fix_module = None
            
            for path in import_paths:
                try:
                    asyncio_fix_module = __import__(path, fromlist=['apply_all_fixes'])
                    logger.info(f"成功导入 {path} 模块")
                    fixes_applied["asyncio_fix_module"] = True
                    
                    # 显式调用应用所有修复函数
                    if hasattr(asyncio_fix_module, 'apply_all_fixes'):
                        result = asyncio_fix_module.apply_all_fixes()
                        logger.info(f"显式应用所有asyncio修复: {result if isinstance(result, dict) else '成功'}")
                        fixes_applied["apply_all_fixes"] = True
                    else:
                        logger.warning(f"{path} 模块没有 apply_all_fixes 函数")
                        fixes_applied["apply_all_fixes"] = False
                    
                    break
                except ImportError:
                    continue
            
            if not asyncio_fix_module:
                logger.warning("⚠️ 无法导入 asyncio_fix 模块")
                fixes_applied["asyncio_fix_module"] = False
        except Exception as e:
            logger.error(f"应用asyncio修复时出错: {str(e)}")
            fixes_applied["asyncio_fix_error"] = str(e)
        
        # 尝试导入和应用HTTP客户端修复
        try:
            import_paths = [
                "backend.worker.utils.http_client",
                "worker.utils.http_client"
            ]
            http_client_module = None
            
            for path in import_paths:
                try:
                    http_client_module = __import__(path, fromlist=['http_client'])
                    logger.info(f"成功导入 {path} 模块")
                    fixes_applied["http_client_module"] = True
                    break
                except ImportError:
                    continue
            
            if not http_client_module:
                logger.warning("⚠️ 无法导入 http_client 模块")
                fixes_applied["http_client_module"] = False
        except Exception as e:
            logger.error(f"导入HTTP客户端模块时出错: {str(e)}")
            fixes_applied["http_client_error"] = str(e)
        
        logger.info(f"事件循环修复状态: {all(fixes_applied.values()) if fixes_applied else False}")
        return fixes_applied
    except Exception as e:
        logger.error(f"确保应用事件循环修复时发生未知错误: {str(e)}")
        return {"unknown_error": str(e)}

# 应用事件循环修复
fixes_applied = ensure_asyncio_fixes()

# 创建Celery实例
celery_app = Celery(
    "worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# 更新Celery配置
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",  # 使用上海时区
    enable_utc=True,  # 内部使用UTC时间
    worker_hijack_root_logger=True,  # 劫持root logger
    worker_redirect_stdouts=True,  # 重定向标准输出
    task_track_started=True,  # 跟踪任务开始时间
    task_soft_time_limit=600,  # 软时间限制10分钟
    task_time_limit=900,  # 硬时间限制15分钟
    worker_max_tasks_per_child=200,  # 每个worker处理200个任务后重启
    worker_concurrency=getattr(settings, 'CELERY_WORKER_CONCURRENCY', 4),  # 并发worker数
)

# 注册任务模块
celery_app.autodiscover_tasks(["worker.tasks"])

# 应用事件循环修复日志
if fixes_applied and VERBOSE_LOGGING:
    logger.info(f"应用的事件循环修复: {fixes_applied}")

# 记录Celery启动状态
logger.info(f"Celery应用已创建: broker={settings.CELERY_BROKER_URL}")
logger.info(f"任务模块已自动发现，并发度: {getattr(settings, 'CELERY_WORKER_CONCURRENCY', 4)}") 