import os
import logging
from typing import Dict, Any, Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class Settings:
    """
    应用配置
    """
    def __init__(self):
        # 应用设置
        self.app_name = os.getenv("APP_NAME", "NewsNow Worker")
        self.app_version = os.getenv("APP_VERSION", "0.1.0")
        self.debug = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
        
        # 日志设置
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        # 控制详细日志输出
        self.verbose_logging = self.log_level.upper() not in ["WARNING", "ERROR"]
        
        # Redis设置
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis_prefix = os.getenv("REDIS_PREFIX", "newsnow:")
        
        # 数据源设置
        self.min_fetch_interval = int(os.getenv("MIN_FETCH_INTERVAL", "300"))  # 最小抓取间隔（秒）
        self.max_fetch_interval = int(os.getenv("MAX_FETCH_INTERVAL", "3600"))  # 最大抓取间隔（秒）
        
        # 缓存设置
        self.cache_ttl = int(os.getenv("CACHE_TTL", "3600"))  # 缓存过期时间（秒）
        self.use_redis_cache = os.getenv("USE_REDIS_CACHE", "False").lower() in ("true", "1", "t")
        
        # API设置
        self.api_host = os.getenv("API_HOST", "0.0.0.0")
        self.api_port = int(os.getenv("API_PORT", "8000"))
        
        # 初始化日志级别
        self._setup_logging()
    
    def _setup_logging(self):
        """
        设置日志级别
        """
        log_level = getattr(logging, self.log_level.upper(), logging.INFO)
        logging.getLogger().setLevel(log_level)
        
        # 设置第三方库的日志级别
        if not self.verbose_logging:
            # 减少第三方库的日志输出
            logging.getLogger("celery").setLevel(logging.WARNING)
            logging.getLogger("kombu").setLevel(logging.WARNING)
            logging.getLogger("amqp").setLevel(logging.WARNING)
            
            # 只在verbose模式输出日志等级信息
            logging.getLogger(__name__).debug(f"Log level set to {self.log_level}")
        else:
            logger.info(f"Log level set to {self.log_level}")
    
    def log_info(self, message):
        """根据日志级别设置选择使用info或debug级别记录日志"""
        if self.verbose_logging:
            logger.info(message)
        else:
            logger.debug(message)
    
    def get_dict(self) -> Dict[str, Any]:
        """
        获取配置字典
        """
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "debug": self.debug,
            "log_level": self.log_level,
            "verbose_logging": self.verbose_logging,
            "redis_url": self.redis_url,
            "redis_prefix": self.redis_prefix,
            "min_fetch_interval": self.min_fetch_interval,
            "max_fetch_interval": self.max_fetch_interval,
            "cache_ttl": self.cache_ttl,
            "use_redis_cache": self.use_redis_cache,
            "api_host": self.api_host,
            "api_port": self.api_port
        }


# 创建全局设置实例
settings = Settings() 