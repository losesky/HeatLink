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

# 先导入自动修复模块，这会自动应用所有修复
# 包括事件循环修复、HTTP客户端修复和缓存修复
try:
    from backend.worker import auto_fix as asyncio_fixes
    logger.info("成功导入了 backend.worker.auto_fix 模块")
    fixes_applied = asyncio_fixes.get_fixes_status()
    for fix_name, status in fixes_applied.items():
        logger.info(f"修复 {fix_name}: {'已应用' if status else '未应用'}")
except ImportError:
    try:
        from worker import auto_fix as asyncio_fixes
        logger.info("成功导入了 worker.auto_fix 模块")
        fixes_applied = asyncio_fixes.get_fixes_status()
        for fix_name, status in fixes_applied.items():
            logger.info(f"修复 {fix_name}: {'已应用' if status else '未应用'}")
    except ImportError:
        logger.warning("⚠️ 无法导入 auto_fix 模块，将尝试直接导入各个修复模块")
        asyncio_fixes = None

# 如果自动修复模块导入失败，尝试单独导入各个修复模块
if asyncio_fixes is None:
    # 导入事件循环修复
    try:
        from backend.worker.asyncio_fix import apply_all_fixes
        logger.info("导入了 backend.worker.asyncio_fix 模块")
        apply_all_fixes()
        logger.info("✅ 已应用事件循环修复")
    except ImportError:
        try:
            from worker.asyncio_fix import apply_all_fixes
            logger.info("导入了 worker.asyncio_fix 模块")
            apply_all_fixes()
            logger.info("✅ 已应用事件循环修复")
        except ImportError:
            logger.warning("❌ 无法导入 asyncio_fix 模块，异步任务可能会出现问题")
            apply_all_fixes = None
    
    # 导入缓存修复
    try:
        from backend.worker.utils import cache_fix
        logger.info("导入了 backend.worker.utils.cache_fix 模块")
    except ImportError:
        try:
            from worker.utils import cache_fix
            logger.info("导入了 worker.utils.cache_fix 模块")
        except ImportError:
            logger.warning("❌ 无法导入 cache_fix 模块，缓存操作可能会出现问题")

# 创建Celery应用
celery_app = Celery(
    "worker",
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/2"),
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1"),
)

# 配置Celery
celery_app.conf.task_routes = {
    "news.*": {"queue": "news-queue"},
}

# 自动发现任务
celery_app.autodiscover_tasks(["worker.tasks"])

# 导入所有任务模块，确保任务注册和定期任务配置被加载
try:
    import worker.tasks
    if VERBOSE_LOGGING:
        logger.info("✅ 成功导入任务模块和定期任务配置")
except ImportError:
    try:
        import backend.worker.tasks
        if VERBOSE_LOGGING:
            logger.info("✅ 成功导入任务模块和定期任务配置")
    except ImportError:
        logger.warning("❌ 无法导入任务模块，定期任务可能无法工作")

if VERBOSE_LOGGING:
    logger.info("✅ 所有修复已应用，Celery Worker将正常处理异步任务") 