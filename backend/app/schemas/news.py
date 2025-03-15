from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class NewsBase(BaseModel):
    title: str
    url: str
    mobile_url: Optional[str] = None
    original_id: str
    source_id: str
    category_id: Optional[int] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    image_url: Optional[str] = None
    published_at: Optional[datetime] = None
    is_top: bool = False
    extra: Optional[Dict[str, Any]] = None


class NewsCreate(NewsBase):
    pass


class NewsUpdate(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None
    mobile_url: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    image_url: Optional[str] = None
    published_at: Optional[datetime] = None
    is_top: Optional[bool] = None
    category_id: Optional[int] = None
    extra: Optional[Dict[str, Any]] = None


class NewsInDB(NewsBase):
    id: int
    created_at: datetime
    updated_at: datetime
    view_count: int = 0
    sentiment_score: Optional[float] = None
    cluster_id: Optional[str] = None

    class Config:
        from_attributes = True


class News(NewsInDB):
    pass


class NewsWithRelations(News):
    source_name: str
    category_name: Optional[str] = None
    tags: List[str] = []


class NewsListItem(BaseModel):
    id: int
    title: str
    url: str
    source_id: str
    source_name: str
    published_at: Optional[datetime] = None
    image_url: Optional[str] = None
    summary: Optional[str] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    is_top: bool = False
    view_count: int = 0
    sentiment_score: Optional[float] = None
    extra: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True 