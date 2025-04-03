from fastapi import APIRouter, Query, Path, Depends, HTTPException
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel
import asyncio
import datetime
from datetime import timedelta

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


class AllNewsResponse(BaseModel):
    """所有新闻源的统一响应模型"""
    source_id: str
    source_name: str
    category: str
    country: str
    language: str
    news: List[NewsItem]
    last_updated: str


class NewsFilter(BaseModel):
    """新闻过滤条件"""
    categories: Optional[List[str]] = None
    countries: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    sources: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class NewsAggregation(BaseModel):
    """新闻聚合结果"""
    total_count: int
    sources_count: int
    categories: Dict[str, int]
    countries: Dict[str, int]
    languages: Dict[str, int]
    date_histogram: Dict[str, int]
    top_keywords: List[Dict[str, Any]]


class UnifiedNewsResponse(BaseModel):
    """统一新闻响应"""
    news: List[NewsItem]
    aggregations: NewsAggregation
    pagination: Dict[str, Any]


class SourceStats(BaseModel):
    """新闻源统计信息"""
    source_id: str
    source_name: str
    category: str
    country: str
    language: str
    news_count: int
    last_updated: Optional[str] = None
    update_interval: Optional[int] = None
    cache_ttl: Optional[int] = None


class NewsStats(BaseModel):
    """新闻统计信息"""
    total_sources: int
    total_news: int
    sources_by_category: Dict[str, int]
    sources_by_country: Dict[str, int]
    sources_by_language: Dict[str, int]
    sources: List[SourceStats]


@router.get("/sources", response_model=List[NewsSource])
async def get_sources():
    """获取所有新闻源"""
    sources = source_manager.get_all_sources()
    
    # 收集所有自定义源的ID
    custom_source_ids = [s.source_id for s in sources if s.source_id.startswith('custom-')]
    
    # 如果有自定义源，从数据库获取它们的元数据
    custom_source_metadata = {}
    if custom_source_ids:
        try:
            from app.db.session import SessionLocal
            from app.models.source import Source
            from app.models.category import Category
            
            # 创建数据库会话
            db = SessionLocal()
            try:
                # 查询所有自定义源的元数据
                custom_sources = db.query(Source).filter(Source.id.in_(custom_source_ids)).all()
                
                # 获取分类信息
                category_ids = [s.category_id for s in custom_sources if s.category_id is not None]
                categories = {}
                if category_ids:
                    for cat in db.query(Category).filter(Category.id.in_(category_ids)).all():
                        categories[cat.id] = cat.slug
                
                # 保存元数据
                for source in custom_sources:
                    category = "general"
                    if source.category_id and source.category_id in categories:
                        category = categories[source.category_id]
                    
                    # 转换timedelta为秒
                    update_interval = source.update_interval.total_seconds() if hasattr(source.update_interval, 'total_seconds') else 1800
                    cache_ttl = source.cache_ttl.total_seconds() if hasattr(source.cache_ttl, 'total_seconds') else 900
                    
                    custom_source_metadata[source.id] = {
                        "name": source.name,
                        "category": category,
                        "country": source.country or "global",
                        "language": source.language or "en",
                        "update_interval": int(update_interval),
                        "cache_ttl": int(cache_ttl)
                    }
            finally:
                db.close()
        except Exception as e:
            import logging
            logger = logging.getLogger("news_api")
            logger.error(f"获取自定义源元数据时出错: {str(e)}")
    
    # 格式化返回数据
    result = []
    for source in sources:
        if source.source_id in custom_source_metadata:
            # 使用数据库中的元数据
            meta = custom_source_metadata[source.source_id]
            result.append({
                "source_id": source.source_id,
                "name": meta["name"],
                "category": meta["category"],
                "country": meta["country"],
                "language": meta["language"],
                "update_interval": meta["update_interval"],
                "cache_ttl": meta["cache_ttl"]
            })
        else:
            # 使用源对象的元数据
            result.append({
            "source_id": source.source_id,
            "name": source.name,
            "category": source.category,
            "country": source.country,
            "language": source.language,
            "update_interval": source.update_interval if isinstance(source.update_interval, int) else int(source.update_interval.total_seconds()) if hasattr(source.update_interval, 'total_seconds') else None,
            "cache_ttl": source.cache_ttl if isinstance(source.cache_ttl, int) else int(source.cache_ttl.total_seconds()) if hasattr(source.cache_ttl, 'total_seconds') else None
            })
    
    return result


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


@router.get("/all", response_model=List[AllNewsResponse])
async def get_all_news(
    force_update: bool = Query(False, description="是否强制更新"),
    category: Optional[str] = Query(None, description="按分类筛选"),
    country: Optional[str] = Query(None, description="按国家筛选"),
    language: Optional[str] = Query(None, description="按语言筛选")
):
    """
    获取所有新闻源的新闻，返回统一的数据结构
    
    - **force_update**: 是否强制更新
    - **category**: 按分类筛选
    - **country**: 按国家筛选
    - **language**: 按语言筛选
    """
    # 根据筛选条件获取新闻源
    sources = source_manager.get_all_sources()
    
    if category:
        sources = [s for s in sources if s.category == category]
    if country:
        sources = [s for s in sources if s.country == country]
    if language:
        sources = [s for s in sources if s.language == language]
    
    # 获取所有新闻
    tasks = []
    for source in sources:
        tasks.append(source_manager.fetch_news(source.source_id, force_update=force_update))
    
    results = await asyncio.gather(*tasks)
    
    # 构建统一的响应
    response = []
    for i, source in enumerate(sources):
        news_items = results[i]
        response.append({
            "source_id": source.source_id,
            "source_name": source.name,
            "category": source.category,
            "country": source.country,
            "language": source.language,
            "news": [item.to_dict() for item in news_items],
            "last_updated": datetime.datetime.now().isoformat()
        })
    
    return response


@router.get("/unified", response_model=List[NewsItem])
async def get_unified_news(
    force_update: bool = Query(False, description="是否强制更新"),
    category: Optional[str] = Query(None, description="按分类筛选"),
    country: Optional[str] = Query(None, description="按国家筛选"),
    language: Optional[str] = Query(None, description="按语言筛选"),
    limit: int = Query(100, description="返回的新闻数量"),
    sort_by: str = Query("published_at", description="排序字段，支持published_at、title"),
    sort_order: str = Query("desc", description="排序方向，支持asc、desc")
):
    """
    获取所有新闻源的新闻，合并为统一的列表
    
    - **force_update**: 是否强制更新
    - **category**: 按分类筛选
    - **country**: 按国家筛选
    - **language**: 按语言筛选
    - **limit**: 返回的新闻数量
    - **sort_by**: 排序字段，支持published_at、title
    - **sort_order**: 排序方向，支持asc、desc
    """
    # 根据筛选条件获取新闻源
    sources = source_manager.get_all_sources()
    
    if category:
        sources = [s for s in sources if s.category == category]
    if country:
        sources = [s for s in sources if s.country == country]
    if language:
        sources = [s for s in sources if s.language == language]
    
    # 获取所有新闻
    tasks = []
    for source in sources:
        tasks.append(source_manager.fetch_news(source.source_id, force_update=force_update))
    
    results = await asyncio.gather(*tasks)
    
    # 合并所有新闻
    all_news = []
    for i, source in enumerate(sources):
        news_items = results[i]
        all_news.extend(news_items)
    
    # 排序
    if sort_by == "published_at":
        all_news.sort(key=lambda x: x.published_at, reverse=(sort_order == "desc"))
    elif sort_by == "title":
        all_news.sort(key=lambda x: x.title, reverse=(sort_order == "desc"))
    
    # 限制数量
    all_news = all_news[:limit]
    
    return [item.to_dict() for item in all_news]


@router.post("/advanced", response_model=UnifiedNewsResponse)
async def get_advanced_news(
    filters: NewsFilter = None,
    page: int = Query(1, description="页码，从1开始"),
    page_size: int = Query(20, description="每页数量"),
    sort_by: str = Query("published_at", description="排序字段，支持published_at、title"),
    sort_order: str = Query("desc", description="排序方向，支持asc、desc"),
    force_update: bool = Query(False, description="是否强制更新")
):
    """
    高级新闻查询接口，支持复杂过滤和聚合
    
    - **filters**: 过滤条件
    - **page**: 页码，从1开始
    - **page_size**: 每页数量
    - **sort_by**: 排序字段
    - **sort_order**: 排序方向
    - **force_update**: 是否强制更新
    """
    filters = filters or NewsFilter()
    
    # 获取所有新闻源
    sources = source_manager.get_all_sources()
    
    # 应用源过滤
    if filters.sources:
        sources = [s for s in sources if s.source_id in filters.sources]
    
    # 应用分类过滤
    if filters.categories:
        sources = [s for s in sources if s.category in filters.categories]
    
    # 应用国家过滤
    if filters.countries:
        sources = [s for s in sources if s.country in filters.countries]
    
    # 应用语言过滤
    if filters.languages:
        sources = [s for s in sources if s.language in filters.languages]
    
    # 获取所有新闻
    tasks = []
    for source in sources:
        tasks.append(source_manager.fetch_news(source.source_id, force_update=force_update))
    
    results = await asyncio.gather(*tasks)
    
    # 合并所有新闻
    all_news = []
    for i, source in enumerate(sources):
        news_items = results[i]
        all_news.extend(news_items)
    
    # 应用日期过滤
    if filters.start_date:
        try:
            start_date = datetime.datetime.fromisoformat(filters.start_date)
            all_news = [n for n in all_news if n.published_at and n.published_at >= start_date]
        except ValueError:
            pass
    
    if filters.end_date:
        try:
            end_date = datetime.datetime.fromisoformat(filters.end_date)
            all_news = [n for n in all_news if n.published_at and n.published_at <= end_date]
        except ValueError:
            pass
    
    # 应用关键词过滤
    if filters.keywords:
        filtered_news = []
        for news in all_news:
            for keyword in filters.keywords:
                if (keyword.lower() in news.title.lower() or 
                    (news.summary and keyword.lower() in news.summary.lower()) or
                    (news.content and keyword.lower() in news.content.lower())):
                    filtered_news.append(news)
                    break
        all_news = filtered_news
    
    # 计算聚合
    total_count = len(all_news)
    sources_count = len(set(n.source_id for n in all_news))
    
    # 分类聚合
    categories = {}
    for news in all_news:
        category = news.category or "未分类"
        categories[category] = categories.get(category, 0) + 1
    
    # 国家聚合
    countries = {}
    for news in all_news:
        country = news.country or "未知"
        countries[country] = countries.get(country, 0) + 1
    
    # 语言聚合
    languages = {}
    for news in all_news:
        language = news.language or "未知"
        languages[language] = languages.get(language, 0) + 1
    
    # 日期直方图
    date_histogram = {}
    for news in all_news:
        if news.published_at:
            date_key = news.published_at.strftime("%Y-%m-%d")
            date_histogram[date_key] = date_histogram.get(date_key, 0) + 1
    
    # 提取关键词
    keywords_count = {}
    for news in all_news:
        # 从标题中提取关键词
        words = news.title.lower().split()
        for word in words:
            if len(word) > 2:  # 忽略太短的词
                keywords_count[word] = keywords_count.get(word, 0) + 1
    
    # 获取前20个关键词
    top_keywords = sorted(
        [{"keyword": k, "count": v} for k, v in keywords_count.items()],
        key=lambda x: x["count"],
        reverse=True
    )[:20]
    
    # 排序
    if sort_by == "published_at":
        all_news.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.min, 
                     reverse=(sort_order == "desc"))
    elif sort_by == "title":
        all_news.sort(key=lambda x: x.title, reverse=(sort_order == "desc"))
    
    # 分页
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paged_news = all_news[start_idx:end_idx]
    
    # 构建响应
    response = {
        "news": [item.to_dict() for item in paged_news],
        "aggregations": {
            "total_count": total_count,
            "sources_count": sources_count,
            "categories": categories,
            "countries": countries,
            "languages": languages,
            "date_histogram": date_histogram,
            "top_keywords": top_keywords
        },
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size,
            "total_items": total_count
        }
    }
    
    return response


@router.get("/stats", response_model=NewsStats)
async def get_news_stats(
    force_update: bool = Query(False, description="是否强制更新")
):
    """
    获取新闻源的统计信息
    
    - **force_update**: 是否强制更新
    """
    # 获取所有新闻源
    sources = source_manager.get_all_sources()
    
    # 统计分类、国家、语言
    categories = {}
    countries = {}
    languages = {}
    
    for source in sources:
        # 统计分类
        category = source.category or "未分类"
        categories[category] = categories.get(category, 0) + 1
        
        # 统计国家
        country = source.country or "未知"
        countries[country] = countries.get(country, 0) + 1
        
        # 统计语言
        language = source.language or "未知"
        languages[language] = languages.get(language, 0) + 1
    
    # 获取每个源的新闻数量
    source_stats = []
    total_news = 0
    
    for source in sources:
        # 获取缓存中的新闻数量
        news_count = len(source_manager.news_cache.get(source.source_id, []))
        total_news += news_count
        
        # 获取最后更新时间
        last_updated = source_manager.last_fetch_time.get(source.source_id)
        last_updated_str = datetime.datetime.fromtimestamp(last_updated).isoformat() if last_updated else None
        
        # 添加源统计
        source_stats.append({
            "source_id": source.source_id,
            "source_name": source.name,
            "category": source.category,
            "country": source.country,
            "language": source.language,
            "news_count": news_count,
            "last_updated": last_updated_str,
            "update_interval": source.update_interval if isinstance(source.update_interval, int) else int(source.update_interval.total_seconds()) if hasattr(source.update_interval, 'total_seconds') else None,
            "cache_ttl": source.cache_ttl if isinstance(source.cache_ttl, int) else int(source.cache_ttl.total_seconds()) if hasattr(source.cache_ttl, 'total_seconds') else None
        })
    
    # 构建响应
    response = {
        "total_sources": len(sources),
        "total_news": total_news,
        "sources_by_category": categories,
        "sources_by_country": countries,
        "sources_by_language": languages,
        "sources": source_stats
    }
    
    return response 