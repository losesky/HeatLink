from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
import redis
import time
from typing import Dict, Any
import logging
from app.core.config import settings
from app.api import deps

# 创建路由器
router = APIRouter()

# 获取日志记录器
logger = logging.getLogger(__name__)

@router.get("", response_model=Dict[str, Any])
async def health_check(db: Session = Depends(deps.get_db)):
    """
    API健康状态检查
    检查API服务器、数据库和Redis连接是否正常
    """
    start_time = time.time()
    health_data = {
        "status": "healthy",
        "timestamp": start_time,
        "uptime": time.time() - start_time,
        "api": {
            "status": "ok"
        },
        "database": {
            "status": "checking"
        },
        "redis": {
            "status": "checking"
        }
    }

    # 检查数据库连接
    try:
        # 执行简单查询以验证连接，使用text()函数包装SQL语句
        db.execute(text("SELECT 1"))
        health_data["database"]["status"] = "ok"
    except SQLAlchemyError as e:
        health_data["database"]["status"] = "error"
        health_data["database"]["error"] = str(e)
        health_data["status"] = "unhealthy"
        logger.error(f"数据库健康检查失败: {str(e)}")

    # 检查Redis连接
    try:
        # 添加超时设置，避免长时间等待
        redis_client = redis.from_url(settings.REDIS_URL, socket_timeout=2.0)
        if redis_client.ping():
            health_data["redis"]["status"] = "ok"
        else:
            health_data["redis"]["status"] = "error"
            health_data["redis"]["error"] = "Redis ping返回False"
            health_data["status"] = "unhealthy"
    except redis.ConnectionError as e:
        health_data["redis"]["status"] = "error"
        health_data["redis"]["error"] = f"Redis连接错误: {str(e)}"
        health_data["status"] = "unhealthy"
        logger.error(f"Redis连接错误: {str(e)}")
    except redis.TimeoutError as e:
        health_data["redis"]["status"] = "error"
        health_data["redis"]["error"] = f"Redis连接超时: {str(e)}"
        health_data["status"] = "unhealthy"
        logger.error(f"Redis连接超时: {str(e)}")
    except Exception as e:
        health_data["redis"]["status"] = "error"
        health_data["redis"]["error"] = f"Redis检查失败: {str(e)}"
        health_data["status"] = "unhealthy"
        logger.error(f"Redis健康检查失败: {str(e)}")

    return health_data 