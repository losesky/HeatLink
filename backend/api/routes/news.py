from fastapi import APIRouter, Query, Path, Depends, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from worker.sources.manager import source_manager
from worker.sources.aggregator import aggregator_manager

router = APIRouter(prefix="/news", tags=["news"])


class NewsItem(BaseModel):
    """新闻项模型"""
    id: str
    title: str
    url: str
    mobile_url: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    image_url: Optional[str] = None
    published_at: Optional[str] = None
    is_top: bool = False
    extra: Dict[str, Any] = {}


class NewsSource(BaseModel):
    """新闻源模型"""
    source_id: str
    name: str
    category: str
    country: str
    language: str
    update_interval: Optional[int] = None
    cache_ttl: Optional[int] = None


class NewsCluster(BaseModel):
    """新闻聚类模型"""
    main_news: NewsItem
    related_news: List[NewsItem]
    sources: List[str]
    keywords: List[str]
    created_at: str
    updated_at: str
    score: float
    news_count: int


@router.get("/sources", response_model=List[NewsSource])
async def get_sources():
    """获取所有新闻源"""
    sources = source_manager.get_all_sources()
    return [
        {
            "source_id": source.source_id,
            "name": source.name,
            "category": source.category,
            "country": source.country,
            "language": source.language,
            "update_interval": source.update_interval if isinstance(source.update_interval, int) else int(source.update_interval.total_seconds()) if hasattr(source.update_interval, 'total_seconds') else None,
            "cache_ttl": source.cache_ttl if isinstance(source.cache_ttl, int) else int(source.cache_ttl.total_seconds()) if hasattr(source.cache_ttl, 'total_seconds') else None
        }
        for source in sources
    ]


@router.get("/sources/{source_id}", response_model=List[NewsItem])
async def get_source_news(
    source_id: str = Path(..., description="新闻源ID"),
    force_update: bool = Query(False, description="是否强制更新")
):
    """获取指定新闻源的新闻"""
    source = source_manager.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"News source not found: {source_id}")
    
    news_items = await source_manager.fetch_news(source_id, force_update=force_update)
    return [item.to_dict() for item in news_items]


@router.get("/category/{category}", response_model=Dict[str, List[NewsItem]])
async def get_category_news(
    category: str = Path(..., description="新闻分类"),
    force_update: bool = Query(False, description="是否强制更新")
):
    """获取指定分类的新闻"""
    news_dict = await source_manager.fetch_news_by_category(category, force_update=force_update)
    
    result = {}
    for source_id, news_items in news_dict.items():
        result[source_id] = [item.to_dict() for item in news_items]
    
    return result


@router.get("/hot", response_model=List[NewsCluster])
async def get_hot_topics(
    limit: int = Query(20, description="返回的热门话题数量"),
    force_update: bool = Query(False, description="是否强制更新")
):
    """获取热门话题"""
    # 更新聚合器
    await aggregator_manager.update(force=force_update)
    
    # 获取热门话题
    hot_topics = aggregator_manager.get_hot_topics(limit=limit)
    return hot_topics


@router.get("/hot/{category}", response_model=List[NewsCluster])
async def get_category_hot_topics(
    category: str = Path(..., description="新闻分类"),
    limit: int = Query(20, description="返回的热门话题数量"),
    force_update: bool = Query(False, description="是否强制更新")
):
    """获取指定分类的热门话题"""
    # 更新聚合器
    await aggregator_manager.update(force=force_update)
    
    # 获取分类热门话题
    category_topics = aggregator_manager.get_topics_by_category(category, limit=limit)
    return category_topics


@router.get("/search", response_model=List[NewsItem])
async def search_news(
    query: str = Query(..., description="搜索关键词"),
    max_results: int = Query(100, description="最大返回结果数")
):
    """搜索新闻"""
    results = await source_manager.search_news(query, max_results=max_results)
    return [item.to_dict() for item in results] 