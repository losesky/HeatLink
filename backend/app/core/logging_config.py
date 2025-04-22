"""
日志配置模块

提供应用程序的日志配置，集中管理各模块的日志级别。
"""

import os
import logging
import logging.config
import logging.handlers
from app.core.config import settings

# 添加ANSI颜色代码
class ColorFormatter(logging.Formatter):
    """为日志添加颜色的格式化器"""
    
    # 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',  # 青色
        'INFO': '\033[32m',   # 绿色
        'WARNING': '\033[33m', # 黄色
        'ERROR': '\033[31m',   # 红色
        'CRITICAL': '\033[41m\033[37m', # 白字红底
        'RESET': '\033[0m'     # 重置颜色
    }
    
    def __init__(self, fmt):
        super().__init__(fmt)
    
    def format(self, record):
        # 保存原始的levelname
        levelname = record.levelname
        # 如果是终端输出，添加颜色
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
            record.msg = f"{self.COLORS[levelname]}{record.msg}{self.COLORS['RESET']}"
        return super().format(record)

def configure_logging():
    """配置应用程序日志"""
    
    # 基本配置
    log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    
    # 日志格式
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # 配置根日志器，使用彩色格式化器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # 清除已有的处理器
    if root_logger.handlers:
        for handler in root_logger.handlers:
            root_logger.removeHandler(handler)
    
    # 创建控制台处理器并设置彩色格式化器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColorFormatter(log_format))
    root_logger.addHandler(console_handler)
    
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
        
        # Web服务器日志 - 调整为WARNING以便过滤掉一般HTTP请求
        "uvicorn": logging.INFO,  # 保留服务器运行信息
        "uvicorn.access": logging.WARNING,  # 只记录警告及以上级别的访问日志，过滤掉307等常规请求
        
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
        
        # 缓存相关日志 - 将日志级别设置为INFO，但通过处理器重定向到专门的文件
        "cache": logging.INFO,  # 缓存管理器专用日志
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
    
    # 设置缓存日志处理器
    # 创建日志目录
    log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../logs'))
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 配置缓存日志处理器
    cache_logger = logging.getLogger('cache')
    cache_logger.propagate = False  # 防止日志传递到父logger，避免在控制台显示
    
    # 创建文件处理器
    cache_log_file = os.path.join(log_dir, 'cache.log')
    cache_handler = logging.handlers.RotatingFileHandler(
        cache_log_file, maxBytes=10*1024*1024, backupCount=5
    )
    cache_handler.setFormatter(logging.Formatter(log_format))
    cache_logger.addHandler(cache_handler)
    
    # 返回根日志器，通常不需要使用
    return logging.getLogger()


def get_logger(name):
    """获取指定名称的日志器"""
    return logging.getLogger(name)


def get_cache_logger():
    """获取缓存专用日志器"""
    return logging.getLogger('cache') 