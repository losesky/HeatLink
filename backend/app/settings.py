#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
应用设置模块
包含应用的全局配置信息
"""

import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Redis配置
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# 通过类导出设置，便于使用时引入
class Settings:
    """应用设置类"""
    
    # Redis
    redis_url = redis_url
    redis_pool_size = 10
    redis_timeout = 5  # 秒
    
    # 缓存
    cache_ttl_default = 3600  # 1小时
    cache_ttl_short = 300     # 5分钟
    cache_ttl_long = 86400    # 24小时
    
    # 应用信息
    app_name = "HeatLink"
    version = "1.0.0"
    
    # 其他配置
    log_level = "INFO"
    debug = os.environ.get("DEBUG", "False").lower() == "true"

# 导出设置实例
settings = Settings() 