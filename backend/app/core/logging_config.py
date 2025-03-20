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
    # 级别说明:
    # - DEBUG: 最详细的调试信息，适用于开发调试
    # - INFO: 一般运行信息，如启动、初始化等
    # - WARNING: 警告信息，表示可能有问题但程序仍能运行
    # - ERROR: 错误信息，表示功能受到影响
    # - CRITICAL: 严重错误，可能导致程序崩溃
    module_levels = {
        # 源适配器日志级别
        "worker.sources.sites": logging.WARNING,  # 初始化信息不显示
        "worker.sources.factory": logging.WARNING,  # 工厂方法信息不显示
        
        # 保留worker.sources其他模块的INFO级别，如API请求、数据处理等
        # "worker.sources": logging.WARNING,  # 所有源相关的日志（注释掉，保留INFO级别）
        
        # 特定源适配器的日志级别单独调整（只抑制警告信息过多的模块）
        "worker.sources.sites.cls": logging.ERROR,  # 财联社只显示错误
        "worker.sources.sites.fastbull": logging.ERROR,  # 快牛只显示错误
        "worker.sources.sites.jin10": logging.ERROR,  # 金十只显示错误
        "worker.sources.sites.thepaper_selenium": logging.ERROR,  # 澎湃新闻只显示错误
        
        # 网络请求日志 - 可选根据需要调整
        "httpx": logging.WARNING,
        "urllib3": logging.WARNING,
        "aiohttp": logging.WARNING,
        "charset_normalizer": logging.WARNING,  # 字符编码检测库的日志
        
        # 数据库日志 - 可选根据需要调整
        "sqlalchemy": logging.WARNING,
        
        # Web服务器日志 - 调整为INFO以便查看API请求
        "uvicorn": logging.INFO,  # 保留服务器运行信息
        "uvicorn.access": logging.INFO,  # 记录API访问
        
        # 其他库日志
        "aiocache": logging.WARNING,
        "aioredis": logging.WARNING,
        "passlib": logging.WARNING,
        
        # API相关日志 - 确保记录API请求信息
        "app.api": logging.INFO,  # API端点日志
        
        # 主应用程序日志 - 保持INFO级别以记录重要操作
        "app": logging.INFO,  # 应用核心
        "worker": logging.INFO,  # 工作线程
        "main": logging.INFO,  # 主程序
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