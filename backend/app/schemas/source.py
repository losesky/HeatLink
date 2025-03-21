from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from app.models.source import SourceType, SourceStatus


class SourceBase(BaseModel):
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    type: SourceType
    status: SourceStatus = SourceStatus.INACTIVE
    update_interval: int = 600  # in seconds
    cache_ttl: int = 300  # in seconds
    category_id: Optional[int] = None
    country: Optional[str] = None
    language: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    priority: Optional[int] = 0


class SourceCreate(SourceBase):
    id: str  # e.g., "baidu", "zhihu"


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    type: Optional[SourceType] = None
    status: Optional[SourceStatus] = None
    update_interval: Optional[int] = None
    cache_ttl: Optional[int] = None
    category_id: Optional[int] = None
    country: Optional[str] = None
    language: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    priority: Optional[int] = None


class SourceInDB(SourceBase):
    id: str
    last_updated: Optional[datetime] = None
    error_count: Optional[int] = 0
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Source(SourceInDB):
    pass


class SourceWithStats(Source):
    news_count: int = 0
    latest_news_time: Optional[datetime] = None


class SourceAlias(BaseModel):
    id: int
    alias: str
    source_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class SourceAliasCreate(BaseModel):
    alias: str
    source_id: str 