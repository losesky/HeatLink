import os
from typing import List, Optional, Dict, Any
from pydantic import field_validator, ConfigDict
from pydantic_settings import BaseSettings
from datetime import timedelta


class Settings(BaseSettings):
    # Application settings
    APP_NAME: str = "HeatLink"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = "Multi-Source News Aggregation System"
    DEBUG: bool = False
    
    # Database settings
    DATABASE_URL: str
    TEST_DATABASE_URL: Optional[str] = None
    
    # Redis settings
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Celery settings
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    
    # Security settings
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS settings
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    ALLOW_ALL_ORIGINS: bool = False  # 新增：外部访问模式开关
    
    # News source settings
    DEFAULT_UPDATE_INTERVAL: int = 600  # 10 minutes
    DEFAULT_CACHE_TTL: int = 300  # 5 minutes
    
    # Proxy settings
    PROXY_REQUIRED_DOMAINS: str = ""
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    # Timezone settings
    TZ: Optional[str] = "UTC"
    PGTZ: Optional[str] = "UTC"
    
    @field_validator("DATABASE_URL")
    def validate_database_url(cls, v: Optional[str]) -> str:
        if not v:
            raise ValueError("DATABASE_URL must be set")
        return v
    
    @field_validator("SECRET_KEY")
    def validate_secret_key(cls, v: Optional[str]) -> str:
        if not v or v == "your-secret-key-here":
            if os.environ.get("DEBUG", "false").lower() == "true":
                return "debug-secret-key-not-secure"
            raise ValueError("SECRET_KEY must be set in production")
        return v
    
    @property
    def proxy_domains(self) -> List[str]:
        if not self.PROXY_REQUIRED_DOMAINS:
            return []
        
        # 处理字符串格式
        if isinstance(self.PROXY_REQUIRED_DOMAINS, str):
            return [domain.strip() for domain in self.PROXY_REQUIRED_DOMAINS.split(",") if domain.strip()]
        
        # 其他类型尝试转换
        try:
            domains_str = str(self.PROXY_REQUIRED_DOMAINS)
            return [domain.strip() for domain in domains_str.split(",") if domain.strip()]
        except:
            return []
    
    @property
    def cors_origins(self) -> List[str]:
        """获取实际应用的CORS来源配置"""
        # 如果允许所有来源，返回["*"]
        if self.ALLOW_ALL_ORIGINS or os.environ.get("ALLOW_ALL_ORIGINS", "").lower() == "true":
            return ["*"]
        return self.CORS_ORIGINS
    
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True
    )


settings = Settings() 