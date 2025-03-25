import datetime
from enum import Enum
from typing import List, Optional
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, Float, Enum as SQLEnum
from sqlalchemy.orm import relationship

from app.db.session import Base


class ProxyProtocol(str, Enum):
    SOCKS5 = "socks5"
    HTTP = "http"
    HTTPS = "https"


class ProxyStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    BANNED = "banned"  # 被目标网站封禁


class ProxyConfig(Base):
    __tablename__ = "proxy_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    protocol = Column(SQLEnum(ProxyProtocol), default=ProxyProtocol.SOCKS5)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(100), nullable=True)
    password = Column(String(100), nullable=True)
    region = Column(String(50), nullable=True)  # 代理服务器所在地区
    status = Column(SQLEnum(ProxyStatus), default=ProxyStatus.ACTIVE)
    priority = Column(Integer, default=0)  # 优先级，数值越高优先级越高
    
    # 性能和监控指标
    max_concurrent = Column(Integer, default=0)  # 最大并发连接数，0表示不限制
    success_rate = Column(Float, default=100.0)  # 成功率百分比
    avg_response_time = Column(Float, default=0.0)  # 平均响应时间（秒）
    last_check_time = Column(DateTime, nullable=True)  # 上次检查时间
    health_check_url = Column(String(512), default="https://www.baidu.com")  # 健康检查URL
    
    # 代理组和标签
    group = Column(String(50), default="default")  # 代理组，可以按组使用不同代理
    tags = Column(String(255), nullable=True)  # 标签，逗号分隔，如"us,fast,stable"
    
    # 统计信息
    total_requests = Column(Integer, default=0)  # 总请求次数
    successful_requests = Column(Integer, default=0)  # 成功请求次数
    failed_requests = Column(Integer, default=0)  # 失败请求次数
    last_error = Column(Text, nullable=True)  # 最后一次错误信息
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    def to_dict(self):
        """转换为字典，用于API响应"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port,
            "username": self.username if self.username else None,
            "region": self.region,
            "status": self.status,
            "priority": self.priority,
            "group": self.group,
            "tags": self.tags.split(",") if self.tags else [],
            "success_rate": self.success_rate,
            "avg_response_time": self.avg_response_time,
            "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
            "total_requests": self.total_requests,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    def get_proxy_url(self):
        """获取代理URL，用于aiohttp等客户端"""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        else:
            return f"{self.protocol}://{self.host}:{self.port}" 