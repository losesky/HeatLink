import datetime
from enum import Enum
from typing import List, Optional
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, ForeignKey, JSON, Interval, Enum as SQLEnum
from sqlalchemy.orm import relationship

from app.db.session import Base


class SourceType(str, Enum):
    API = "API"
    WEB = "WEB"
    RSS = "RSS"
    MIXED = "MIXED"


class SourceStatus(str, Enum):
    ACTIVE = "active"
    ERROR = "error"
    WARNING = "warning"
    INACTIVE = "inactive"


class Source(Base):
    __tablename__ = "sources"
    
    id = Column(String(50), primary_key=True)  # e.g., "baidu", "zhihu"
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    url = Column(String(512), nullable=True)
    type = Column(SQLEnum(SourceType), nullable=False)  # API, WEB, RSS, MIXED
    # active 字段已移除，使用 status 字段代替
    # active = Column(Boolean, default=True)
    update_interval = Column(Interval, default=datetime.timedelta(minutes=10))
    cache_ttl = Column(Interval, default=datetime.timedelta(minutes=5))
    last_updated = Column(DateTime, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    country = Column(String(50), nullable=True)  # Country/region
    language = Column(String(20), nullable=True)  # Language
    config = Column(JSON, nullable=True)  # Source-specific configuration (e.g., request headers, parsing rules)
    priority = Column(Integer, default=0)  # Priority, higher means higher priority
    error_count = Column(Integer, default=0)  # Error count
    last_error = Column(Text, nullable=True)  # Last error message
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    status = Column(SQLEnum(SourceStatus), default=SourceStatus.INACTIVE)
    news_count = Column(Integer, default=0)  # 新闻数量
    
    # 代理相关字段
    need_proxy = Column(Boolean, default=False)  # 是否需要使用代理
    proxy_fallback = Column(Boolean, default=True)  # 代理失败时是否尝试直连
    proxy_group = Column(String(50), nullable=True)  # 代理分组，可用于使用不同的代理组
    
    # Relationships
    news = relationship("News", back_populates="source")
    category = relationship("Category", back_populates="sources")
    aliases = relationship("SourceAlias", back_populates="source")
    stats = relationship("SourceStats", back_populates="source")


class SourceAlias(Base):
    __tablename__ = "source_aliases"
    
    id = Column(Integer, primary_key=True, index=True)
    alias = Column(String(50), nullable=False, unique=True)
    source_id = Column(String(50), ForeignKey("sources.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    source = relationship("Source", back_populates="aliases") 