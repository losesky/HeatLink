"""
日志配置模块

提供应用程序的日志配置，集中管理各模块的日志级别。
"""

import os
import logging
import logging.config
from app.core.config import settings

def configure_logging():
    """配置应用程序日志"""
    
    # 基本配置
    log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    
    # 日志格式
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # 基础配置
    logging.basicConfig(
        level=log_level,
        format=log_format
    )
    
    # 设置特定模块的日志级别
    module_levels = {
        # 源适配器日志 - 设置为WARNING以屏蔽初始化URL和配置的INFO消息
        "worker.sources.sites": logging.WARNING,
        
        # 网络请求日志 - 可选根据需要调整
        "httpx": logging.WARNING,
        "urllib3": logging.WARNING,
        "aiohttp": logging.WARNING,
        
        # 数据库日志 - 可选根据需要调整
        "sqlalchemy": logging.WARNING,
        
        # Web服务器日志 - 调整为WARNING以减少访问日志量
        "uvicorn": logging.INFO,
        "uvicorn.access": logging.WARNING,
        
        # 其他库日志
        "aiocache": logging.WARNING,
        "aioredis": logging.WARNING,
        "passlib": logging.WARNING,
    }
    
    # 应用模块级别设置
    for module, level in module_levels.items():
        logging.getLogger(module).setLevel(level)
    
    # 如果是DEBUG模式，可以为某些关键模块启用更详细的日志
    if settings.DEBUG:
        # 主应用日志保持INFO以上
        logging.getLogger("app").setLevel(logging.INFO)
        # API端点可以看到DEBUG信息
        logging.getLogger("app.api").setLevel(logging.DEBUG)
    
    # 返回根日志器，通常不需要使用
    return logging.getLogger()


def get_logger(name):
    """获取指定名称的日志器"""
    return logging.getLogger(name) 