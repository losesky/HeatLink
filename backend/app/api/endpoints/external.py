from typing import Any, List, Dict, Optional
import asyncio
import logging
from datetime import datetime, timezone
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Path, Depends
from pydantic import BaseModel

from worker.sources.factory import NewsSourceFactory
from worker.sources.base import NewsSource, NewsItemModel
from worker.sources.aggregator import aggregator_manager
from worker.sources.manager import source_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("external_api")

router = APIRouter()

# 模型定义
class SourceInfo(BaseModel):
    """新闻源信息"""
    source_id: str
    name: str
    category: str
    country: str
    language: str
    update_interval: Optional[int] = None
    cache_ttl: Optional[int] = None
    description: Optional[str] = None


class NewsItem(BaseModel):
    """新闻项"""
    id: str
    title: str
    url: str
    source_id: str
    source_name: str
    published_at: Optional[str] = None
    updated_at: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    author: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = []
    image_url: Optional[str] = None
    language: Optional[str] = None
    country: Optional[str] = None
    extra: Dict[str, Any] = {}


class SourceResponse(BaseModel):
    """新闻源响应"""
    source: SourceInfo
    news_count: int
    news: List[NewsItem]
    fetch_time: float


class SourcesResponse(BaseModel):
    """所有新闻源响应"""
    total_sources: int
    sources: List[SourceInfo]


class SourcesStatsResponse(BaseModel):
    """新闻源统计响应"""
    total_sources: int
    categories: Dict[str, int]
    countries: Dict[str, int]
    languages: Dict[str, int]
    sources: List[Dict[str, Any]]


class SourceComparisonResponse(BaseModel):
    """新闻源比较响应"""
    sources: Dict[str, Dict[str, Any]]


class AllSourcesResponse(BaseModel):
    """所有新闻源的新闻响应"""
    summary: Dict[str, Any]
    successful_sources: List[Dict[str, Any]]
    failed_sources: List[Dict[str, Any]]
    news: List[Dict[str, Any]]


class UnifiedNewsItem(BaseModel):
    """统一格式的新闻项"""
    id: str
    title: str
    url: str
    source_id: str
    source_name: str
    category: str
    published_at: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    image_url: Optional[str] = None
    country: Optional[str] = None
    language: Optional[str] = None
    extra: Dict[str, Any] = {}


class UnifiedNewsResponse(BaseModel):
    """统一格式的新闻响应"""
    total: int
    page: int
    page_size: int
    total_pages: int
    news: List[UnifiedNewsItem]
    filters: Dict[str, Any]


class HotNewsResponse(BaseModel):
    """热门新闻响应"""
    hot_news: List[UnifiedNewsItem]
    recommended_news: List[UnifiedNewsItem]
    categories: Dict[str, List[UnifiedNewsItem]]


class SearchResponse(BaseModel):
    """搜索响应"""
    total: int
    page: int
    page_size: int
    total_pages: int
    query: str
    results: List[UnifiedNewsItem]


# 实用函数
async def close_source(source):
    """Close the data source and release resources"""
    if source is None:
        return
    
    try:
        # Call close method
        if hasattr(source, 'close'):
            try:
                await source.close()
                return  # If successfully closed, return directly
            except Exception as e:
                logger.warning(f"Error calling close() method: {str(e)}")
        
        # Try to close http_client
        if hasattr(source, '_http_client') and source._http_client is not None:
            # Access _http_client attribute directly
            if hasattr(source._http_client, 'close'):
                await source._http_client.close()
        
        # Try to close aiohttp sessions
        import aiohttp
        import inspect
        for attr_name in dir(source):
            if attr_name.startswith('_'):
                continue
                
            try:
                # Skip property accessors and coroutines
                attr = getattr(source.__class__, attr_name, None)
                if attr and (inspect.iscoroutine(attr) or inspect.isawaitable(attr) or 
                           inspect.iscoroutinefunction(attr) or isinstance(attr, property)):
                    continue
                
                # Get instance attribute
                attr = getattr(source, attr_name)
                
                # Close aiohttp session
                if isinstance(attr, aiohttp.ClientSession) and not attr.closed:
                    await attr.close()
            except (AttributeError, TypeError):
                # Skip coroutine properties or other attributes that cannot be accessed directly
                pass
    except Exception as e:
        logger.warning(f"Error closing source: {str(e)}")


async def fetch_source_news(source_type: str, timeout: int = 60) -> Dict[str, Any]:
    """获取指定新闻源的新闻"""
    result = {
        "source_id": source_type,
        "success": False,
        "news": [],
        "error": None,
        "count": 0,
        "elapsed_time": 0
    }
    
    logger.info(f"Fetching news from source: {source_type}")
    
    # 创建数据源
    source = None
    try:
        source = NewsSourceFactory.create_source(source_type)
        
        if source is None:
            error_msg = f"无法创建新闻源: {source_type}"
            result["error"] = error_msg
            logger.error(error_msg)
            return result
        
        # 获取数据
        start_time = time.time()
        try:
            # 设置超时
            fetch_task = asyncio.create_task(source.get_news(force_update=True))
            news_items = await asyncio.wait_for(fetch_task, timeout=timeout)
            elapsed_time = time.time() - start_time
            
            # 记录结果
            result["success"] = True
            result["news"] = news_items
            result["count"] = len(news_items) if news_items else 0
            result["elapsed_time"] = elapsed_time
            
            logger.info(f"Fetch successful: {len(news_items) if news_items else 0} items in {elapsed_time:.2f}s")
        except asyncio.TimeoutError:
            elapsed_time = time.time() - start_time
            error_msg = f"获取超时，超过 {timeout}s"
            result["error"] = error_msg
            result["elapsed_time"] = elapsed_time
            logger.error(error_msg)
        except Exception as e:
            elapsed_time = time.time() - start_time
            error_msg = f"获取数据出错: {str(e)}"
            result["error"] = error_msg
            result["elapsed_time"] = elapsed_time
            logger.error(error_msg)
    except Exception as e:
        error_msg = f"创建新闻源出错: {str(e)}"
        result["error"] = error_msg
        logger.error(error_msg)
    finally:
        # 关闭数据源
        if source:
            await close_source(source)
    
    return result


@router.get("/sources", response_model=SourcesResponse)
async def get_sources():
    """
    获取所有可用的新闻源信息
    """
    try:
        # 获取所有可用的源类型
        source_types = NewsSourceFactory.get_available_sources()
        
        # 创建并获取源实例
        sources = []
        for source_type in source_types:
            try:
                source = NewsSourceFactory.create_source(source_type)
                if source:
                    sources.append(source)
            except Exception as e:
                logger.error(f"创建源 {source_type} 时出错: {str(e)}")
        
        # 构建响应
        source_info_list = []
        for source in sources:
            try:
                source_info = SourceInfo(
                    source_id=source.source_id,
                    name=source.name,
                    category=source.category or "unknown",
                    country=source.country or "unknown",
                    language=source.language or "unknown",
                    update_interval=source.update_interval,
                    cache_ttl=source.cache_ttl,
                    description=getattr(source, 'description', None) or source.__class__.__doc__
                )
                source_info_list.append(source_info)
            except Exception as e:
                logger.error(f"处理源 {source.source_id} 时出错: {str(e)}")
        
        # 关闭所有数据源
        for source in sources:
            await close_source(source)
        
        return SourcesResponse(
            total_sources=len(source_info_list),
            sources=source_info_list
        )
    except Exception as e:
        logger.error(f"获取所有源信息出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取新闻源信息出错: {str(e)}")


@router.get("/source/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: str = Path(..., description="新闻源ID"),
    timeout: int = Query(60, description="获取超时时间（秒）"),
):
    """
    获取指定新闻源的信息和最新新闻
    """
    try:
        # 创建数据源
        source = NewsSourceFactory.create_source(source_id)
        
        if source is None:
            raise HTTPException(status_code=404, detail=f"找不到新闻源: {source_id}")
        
        # 获取数据源信息
        source_info = SourceInfo(
            source_id=source.source_id,
            name=source.name,
            category=source.category or "unknown",
            country=source.country or "unknown",
            language=source.language or "unknown",
            update_interval=source.update_interval,
            cache_ttl=source.cache_ttl,
            description=getattr(source, 'description', None) or source.__class__.__doc__
        )
        
        # 获取新闻
        result = await fetch_source_news(source_id, timeout)
        
        news_items = []
        if result["success"] and result["news"]:
            for item in result["news"]:
                try:
                    # 处理发布时间，确保格式一致
                    published_at_str = None
                    if item.published_at:
                        try:
                            # 如果是字符串，尝试解析
                            if isinstance(item.published_at, str):
                                dt = datetime.fromisoformat(item.published_at)
                            else:
                                dt = item.published_at
                            
                            # 统一转换为无时区的ISO格式字符串
                            if dt.tzinfo is not None:
                                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                            published_at_str = dt.isoformat()
                        except Exception as e:
                            logger.warning(f"处理发布时间出错: {e}, 源: {source.source_id}, 值: {item.published_at}")
                    
                    news_item = NewsItem(
                        id=item.id,
                        title=item.title,
                        url=item.url,
                        source_id=item.source_id,
                        source_name=source.name,
                        published_at=published_at_str,
                        updated_at=item.updated_at.isoformat() if hasattr(item, 'updated_at') and item.updated_at else None,
                        summary=item.summary,
                        content=item.content,
                        author=getattr(item, 'author', None),
                        category=source.category,
                        tags=getattr(item, 'tags', []),
                        image_url=item.image_url,
                        language=source.language,
                        country=source.country,
                        extra=item.extra
                    )
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"处理新闻项时出错: {str(e)}")
        
        return SourceResponse(
            source=source_info,
            news_count=len(news_items),
            news=news_items,
            fetch_time=result["elapsed_time"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取新闻源 {source_id} 出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取新闻源出错: {str(e)}")


@router.get("/stats", response_model=SourcesStatsResponse)
async def get_sources_stats():
    """
    获取所有新闻源的统计信息
    """
    try:
        # 获取所有可用的源类型
        source_types = NewsSourceFactory.get_available_sources()
        
        # 创建并获取源实例
        sources = []
        for source_type in source_types:
            try:
                source = NewsSourceFactory.create_source(source_type)
                if source:
                    sources.append(source)
            except Exception as e:
                logger.error(f"创建源 {source_type} 时出错: {str(e)}")
        
        # 统计信息
        categories = {}
        countries = {}
        languages = {}
        source_stats = []
        
        # 处理每个源
        for source in sources:
            try:
                # 更新分类统计
                category = source.category or "unknown"
                categories[category] = categories.get(category, 0) + 1
                
                # 更新国家统计
                country = source.country or "unknown"
                countries[country] = countries.get(country, 0) + 1
                
                # 更新语言统计
                language = source.language or "unknown"
                languages[language] = languages.get(language, 0) + 1
                
                # 收集源信息
                source_info = {
                    "source_id": source.source_id,
                    "name": source.name,
                    "category": category,
                    "country": country,
                    "language": language,
                    "update_interval": source.update_interval,
                    "cache_ttl": source.cache_ttl
                }
                source_stats.append(source_info)
            except Exception as e:
                logger.error(f"处理源 {source.source_id} 统计信息时出错: {str(e)}")
        
        # 关闭所有数据源
        for source in sources:
            await close_source(source)
        
        return SourcesStatsResponse(
            total_sources=len(sources),
            categories=categories,
            countries=countries,
            languages=languages,
            sources=source_stats
        )
    except Exception as e:
        logger.error(f"获取源统计信息出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取统计信息出错: {str(e)}")


@router.get("/unified", response_model=UnifiedNewsResponse)
async def get_unified_news(
    background_tasks: BackgroundTasks,
    page: int = Query(1, description="页码，从1开始"),
    page_size: int = Query(20, description="每页数量"),
    category: Optional[str] = Query(None, description="按分类筛选"),
    country: Optional[str] = Query(None, description="按国家筛选"),
    language: Optional[str] = Query(None, description="按语言筛选"),
    source_id: Optional[str] = Query(None, description="按新闻源ID筛选"),
    keyword: Optional[str] = Query(None, description="按关键词筛选"),
    sort_by: str = Query("published_at", description="排序字段，支持published_at、title"),
    sort_order: str = Query("desc", description="排序方向，支持asc、desc"),
    timeout: int = Query(60, description="获取超时时间（秒）"),
    max_concurrent: int = Query(5, description="最大并发数")
):
    """
    获取统一格式的新闻列表，支持分页和筛选
    """
    # 创建记录器并设置名称
    logger = logging.getLogger("external_api")
    
    try:
        # 获取所有可用的源类型
        source_types = NewsSourceFactory.get_available_sources()
        
        # 创建并获取源实例
        all_sources = []
        for source_type in source_types:
            try:
                source = NewsSourceFactory.create_source(source_type)
                if source:
                    all_sources.append(source)
            except Exception as e:
                logger.error(f"创建源 {source_type} 时出错: {str(e)}")
        
        # 筛选符合条件的源
        filtered_sources = []
        for source in all_sources:
            # 关闭不需要的源
            if (category and source.category != category) or \
               (country and source.country != country) or \
               (language and source.language != language) or \
               (source_id and source.source_id != source_id):
                await close_source(source)
                continue
            
            filtered_sources.append(source)
        
        # 如果没有符合条件的源，直接返回空结果
        if not filtered_sources:
            logger.warning(f"没有符合条件的新闻源，筛选条件：category={category}, country={country}, language={language}, source_id={source_id}")
            return UnifiedNewsResponse(
                total=0,
                page=page,
                page_size=page_size,
                total_pages=0,
                news=[],
                filters={
                    "category": category,
                    "country": country,
                    "language": language,
                    "source_id": source_id,
                    "keyword": keyword,
                    "sort_by": sort_by,
                    "sort_order": sort_order
                }
            )
        
        # 限制并发的信号量
        semaphore = asyncio.Semaphore(max_concurrent)
        
        # 并发获取每个源的新闻
        async def fetch_with_semaphore(source_id: str) -> Dict[str, Any]:
            async with semaphore:
                return await fetch_source_news(source_id, timeout)
                
        # 创建获取任务
        source_ids = [source.source_id for source in filtered_sources]
        tasks = [fetch_with_semaphore(source_id) for source_id in source_ids]
        
        # 执行所有任务
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        all_news = []
        source_map = {source.source_id: source for source in filtered_sources}
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"获取源 {source_ids[i]} 新闻时出错: {str(result)}")
                continue
            
            if not result["success"] or not result["news"]:
                continue
            
            source = source_map.get(result["source_id"])
            if not source:
                continue
            
            # 处理新闻项
            for item in result["news"]:
                try:
                    # 如果有关键词筛选，检查标题是否包含关键词
                    if keyword and keyword.lower() not in item.title.lower():
                        continue
                    
                    # 处理发布时间，确保格式一致
                    published_at_str = None
                    if item.published_at:
                        try:
                            # 如果是字符串，尝试解析
                            if isinstance(item.published_at, str):
                                dt = datetime.fromisoformat(item.published_at)
                            else:
                                dt = item.published_at
                            
                            # 统一转换为无时区的ISO格式字符串
                            if dt.tzinfo is not None:
                                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                            published_at_str = dt.isoformat()
                        except Exception as e:
                            logger.warning(f"处理发布时间出错: {e}, 源: {source.source_id}, 值: {item.published_at}")
                    
                    news_item = UnifiedNewsItem(
                        id=item.id,
                        title=item.title,
                        url=item.url,
                        source_id=item.source_id,
                        source_name=source.name,
                        category=source.category or "unknown",
                        published_at=published_at_str,
                        summary=item.summary,
                        content=item.content,
                        image_url=item.image_url,
                        country=source.country or "unknown",
                        language=source.language or "unknown",
                        extra=item.extra
                    )
                    all_news.append(news_item)
                except Exception as e:
                    logger.error(f"处理新闻项时出错: {str(e)}", exc_info=True)
        
        # 排序
        def get_published_at(item):
            if not item.published_at:
                return datetime.min
            try:
                # 解析 ISO 格式的日期时间字符串
                dt = datetime.fromisoformat(item.published_at)
                # 如果有时区信息，转换为 UTC 无时区
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt
            except Exception as e:
                logger.warning(f"解析日期时间出错: {e}, 值: {item.published_at}")
                return datetime.min
        
        if sort_by == "published_at":
            reverse = (sort_order.lower() == "desc")
            all_news.sort(key=get_published_at, reverse=reverse)
        elif sort_by == "title":
            reverse = (sort_order.lower() == "desc")
            all_news.sort(key=lambda x: x.title, reverse=reverse)
        
        # 分页
        total = len(all_news)
        total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 0
        start = (page - 1) * page_size
        end = start + page_size
        paginated_news = all_news[start:end] if start < total else []
        
        # 后台任务：关闭所有源
        async def cleanup():
            for source in filtered_sources:
                await close_source(source)
        
        background_tasks.add_task(cleanup)
        
        # 返回响应
        return UnifiedNewsResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            news=paginated_news,
            filters={
                "category": category,
                "country": country,
                "language": language,
                "source_id": source_id,
                "keyword": keyword,
                "sort_by": sort_by,
                "sort_order": sort_order
            }
        )
    except Exception as e:
        # 记录详细错误信息并包含堆栈跟踪
        logger.error(f"获取统一格式新闻出错: {str(e)}", exc_info=True)
        # 返回错误响应
        raise HTTPException(
            status_code=500, 
            detail=f"获取新闻出错: {str(e)}"
        )


@router.get("/hot", response_model=HotNewsResponse)
async def get_hot_news(
    background_tasks: BackgroundTasks,
    hot_limit: int = Query(10, description="热门新闻数量"),
    recommended_limit: int = Query(10, description="推荐新闻数量"),
    category_limit: int = Query(5, description="每个分类的新闻数量"),
    timeout: int = Query(60, description="获取超时时间（秒）"),
    force_update: bool = Query(False, description="是否强制更新")
):
    """
    获取热门新闻、推荐新闻和各分类的新闻
    """
    try:
        # 获取热门新闻数据
        news_data = await aggregator_manager.get_aggregated_news(force_update=force_update)
        if not news_data:
            raise HTTPException(status_code=500, detail="获取聚合新闻失败")
        
        # 处理热门新闻
        hot_news = []
        for item in news_data.get("hot_news", [])[:hot_limit]:
            try:
                # 处理发布时间，确保格式一致
                published_at_str = None
                if item.get("published_at"):
                    try:
                        # 如果是字符串，尝试解析
                        if isinstance(item.get("published_at"), str):
                            dt = datetime.fromisoformat(item.get("published_at"))
                        else:
                            dt = item.get("published_at")
                        
                        # 统一转换为无时区的ISO格式字符串
                        if dt.tzinfo is not None:
                            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                        published_at_str = dt.isoformat()
                    except Exception as e:
                        logger.warning(f"处理发布时间出错: {e}, 源: {item.get('source_id')}, 值: {item.get('published_at')}")
                
                news_item = UnifiedNewsItem(
                    id=item.get("id"),
                    title=item.get("title"),
                    url=item.get("url"),
                    source_id=item.get("source_id"),
                    source_name=item.get("source_name"),
                    category=item.get("category", "unknown"),
                    published_at=published_at_str,
                    summary=item.get("summary"),
                    content=item.get("content"),
                    image_url=item.get("image_url"),
                    country=item.get("country"),
                    language=item.get("language"),
                    extra=item.get("extra", {})
                )
                hot_news.append(news_item)
            except Exception as e:
                logger.error(f"处理热门新闻项时出错: {str(e)}")
        
        # 处理推荐新闻
        recommended_news = []
        for item in news_data.get("recommended_news", [])[:recommended_limit]:
            try:
                # 处理发布时间，确保格式一致
                published_at_str = None
                if item.get("published_at"):
                    try:
                        # 如果是字符串，尝试解析
                        if isinstance(item.get("published_at"), str):
                            dt = datetime.fromisoformat(item.get("published_at"))
                        else:
                            dt = item.get("published_at")
                        
                        # 统一转换为无时区的ISO格式字符串
                        if dt.tzinfo is not None:
                            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                        published_at_str = dt.isoformat()
                    except Exception as e:
                        logger.warning(f"处理发布时间出错: {e}, 源: {item.get('source_id')}, 值: {item.get('published_at')}")
                
                news_item = UnifiedNewsItem(
                    id=item.get("id"),
                    title=item.get("title"),
                    url=item.get("url"),
                    source_id=item.get("source_id"),
                    source_name=item.get("source_name"),
                    category=item.get("category", "unknown"),
                    published_at=published_at_str,
                    summary=item.get("summary"),
                    content=item.get("content"),
                    image_url=item.get("image_url"),
                    country=item.get("country"),
                    language=item.get("language"),
                    extra=item.get("extra", {})
                )
                recommended_news.append(news_item)
            except Exception as e:
                logger.error(f"处理推荐新闻项时出错: {str(e)}")
        
        # 处理分类新闻
        categories = {}
        for category, items in news_data.get("categories", {}).items():
            category_news = []
            for item in items[:category_limit]:
                try:
                    # 处理发布时间，确保格式一致
                    published_at_str = None
                    if item.get("published_at"):
                        try:
                            # 如果是字符串，尝试解析
                            if isinstance(item.get("published_at"), str):
                                dt = datetime.fromisoformat(item.get("published_at"))
                            else:
                                dt = item.get("published_at")
                            
                            # 统一转换为无时区的ISO格式字符串
                            if dt.tzinfo is not None:
                                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                            published_at_str = dt.isoformat()
                        except Exception as e:
                            logger.warning(f"处理发布时间出错: {e}, 源: {item.get('source_id')}, 值: {item.get('published_at')}")
                    
                    news_item = UnifiedNewsItem(
                        id=item.get("id"),
                        title=item.get("title"),
                        url=item.get("url"),
                        source_id=item.get("source_id"),
                        source_name=item.get("source_name"),
                        category=category,
                        published_at=published_at_str,
                        summary=item.get("summary"),
                        content=item.get("content"),
                        image_url=item.get("image_url"),
                        country=item.get("country"),
                        language=item.get("language"),
                        extra=item.get("extra", {})
                    )
                    category_news.append(news_item)
                except Exception as e:
                    logger.error(f"处理分类 {category} 新闻项时出错: {str(e)}")
            
            if category_news:
                categories[category] = category_news
        
        # 关闭所有源（在后台进行）
        async def cleanup():
            for source in source_manager.get_all_sources():
                await close_source(source)
        
        background_tasks.add_task(cleanup)
        
        return HotNewsResponse(
            hot_news=hot_news,
            recommended_news=recommended_news,
            categories=categories
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取热门新闻出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取热门新闻出错: {str(e)}")


@router.get("/search", response_model=SearchResponse)
async def search_news(
    query: str = Query(..., description="搜索关键词"),
    page: int = Query(1, description="页码，从1开始"),
    page_size: int = Query(20, description="每页数量"),
    category: Optional[str] = Query(None, description="按分类筛选"),
    country: Optional[str] = Query(None, description="按国家筛选"),
    language: Optional[str] = Query(None, description="按语言筛选"),
    source_id: Optional[str] = Query(None, description="按新闻源ID筛选"),
    max_results: int = Query(100, description="最大返回结果数")
):
    """
    搜索新闻
    """
    try:
        search_results = await aggregator_manager.search_news(
            query=query,
            max_results=max_results,
            category=category,
            country=country,
            language=language,
            source_id=source_id
        )
        
        # 处理搜索结果
        results = []
        for item in search_results:
            try:
                # 处理发布时间，确保格式一致
                published_at_str = None
                if item.get("published_at"):
                    try:
                        # 如果是字符串，尝试解析
                        if isinstance(item.get("published_at"), str):
                            dt = datetime.fromisoformat(item.get("published_at"))
                        else:
                            dt = item.get("published_at")
                        
                        # 统一转换为无时区的ISO格式字符串
                        if dt.tzinfo is not None:
                            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                        published_at_str = dt.isoformat()
                    except Exception as e:
                        logger.warning(f"处理发布时间出错: {e}, 源: {item.get('source_id')}, 值: {item.get('published_at')}")
                
                news_item = UnifiedNewsItem(
                    id=item.get("id"),
                    title=item.get("title"),
                    url=item.get("url"),
                    source_id=item.get("source_id"),
                    source_name=item.get("source_name"),
                    category=item.get("category", "unknown"),
                    published_at=published_at_str,
                    summary=item.get("summary"),
                    content=item.get("content"),
                    image_url=item.get("image_url"),
                    country=item.get("country"),
                    language=item.get("language"),
                    extra=item.get("extra", {})
                )
                results.append(news_item)
            except Exception as e:
                logger.error(f"处理搜索结果项时出错: {str(e)}")
        
        # 分页
        total = len(results)
        total_pages = (total + page_size - 1) // page_size
        start = (page - 1) * page_size
        end = start + page_size
        paginated_results = results[start:end] if start < total else []
        
        return SearchResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            query=query,
            results=paginated_results
        )
    except Exception as e:
        logger.error(f"搜索新闻出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"搜索新闻出错: {str(e)}")


@router.get("/source-types", response_model=List[str])
async def get_source_types():
    """
    获取所有可用的新闻源类型
    
    返回新闻系统支持的所有新闻源类型ID列表
    """
    try:
        source_types = NewsSourceFactory.get_available_sources()
        return sorted(source_types)
    except Exception as e:
        logger.error(f"获取新闻源类型失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取新闻源类型失败: {str(e)}")


@router.get("/test-source/{source_id}")
async def test_source(
    source_id: str,
    timeout: int = Query(60, description="超时时间（秒）")
):
    """
    测试单个新闻源
    
    测试指定新闻源是否可以正常获取数据，返回测试结果包括成功状态、获取到的新闻数量和耗时
    
    - **source_id**: 新闻源ID
    - **timeout**: 超时时间（秒）
    """
    source = None
    try:
        start_time = time.time()
        source = NewsSourceFactory.create_source(source_id)
        
        if not source:
            raise HTTPException(status_code=404, detail=f"找不到新闻源: {source_id}")
        
        # 设置超时
        try:
            fetch_task = asyncio.create_task(source.fetch())
            items = await asyncio.wait_for(fetch_task, timeout=timeout)
            elapsed_time = time.time() - start_time
            
            # 返回测试结果
            return {
                "success": True,
                "source_id": source_id,
                "items_count": len(items) if items else 0,
                "elapsed_time": elapsed_time
            }
        except asyncio.TimeoutError:
            elapsed_time = time.time() - start_time
            return {
                "success": False,
                "source_id": source_id,
                "items_count": 0,
                "elapsed_time": elapsed_time,
                "error": f"获取超时，超过 {timeout} 秒"
            }
    except Exception as e:
        elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
        return {
            "success": False,
            "source_id": source_id,
            "items_count": 0,
            "elapsed_time": elapsed_time,
            "error": str(e)
        }
    finally:
        # 确保源被正确关闭
        if source:
            await close_source(source)


@router.get("/test-all-sources")
async def test_all_sources(
    background_tasks: BackgroundTasks,
    timeout: int = Query(60, description="每个源的超时时间（秒）"),
    max_concurrent: int = Query(5, description="最大并发测试数量"),
    source_ids: Optional[List[str]] = Query(None, description="指定要测试的源ID列表，为空则测试所有")
):
    """
    测试所有新闻源
    
    测试系统中所有新闻源或指定的新闻源，返回测试结果摘要和详情
    
    - **timeout**: 每个源的超时时间（秒）
    - **max_concurrent**: 最大并发测试数量
    - **source_ids**: 指定要测试的源ID列表，为空则测试所有
    """
    try:
        # 获取要测试的所有源
        all_source_ids = source_ids or NewsSourceFactory.get_available_sources()
        
        # 创建信号量以限制并发数
        semaphore = asyncio.Semaphore(max_concurrent)
        
        # 定义带信号量的测试函数
        async def test_with_semaphore(source_id: str):
            async with semaphore:
                return await test_source(source_id, timeout)
        
        # 创建所有任务
        tasks = [test_with_semaphore(source_id) for source_id in all_source_ids]
        
        # 开始计时
        total_start_time = time.time()
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks)
        
        # 计算总耗时
        total_elapsed_time = time.time() - total_start_time
        
        # 分离成功和失败的结果
        successful_results = [r for r in results if r["success"]]
        failed_results = [r for r in results if not r["success"]]
        
        # 添加后台清理任务
        async def cleanup():
            from worker.utils.http_client import http_client
            await http_client.close()
        
        background_tasks.add_task(cleanup)
        
        # 返回结果
        return {
            "summary": {
                "total_sources": len(results),
                "successful_sources": len(successful_results),
                "failed_sources": len(failed_results),
                "success_rate": f"{len(successful_results) / len(results) * 100:.1f}%" if results else "0%",
                "total_time": f"{total_elapsed_time:.2f}s"
            },
            "successful_sources": successful_results,
            "failed_sources": failed_results
        }
    except Exception as e:
        logger.error(f"测试所有新闻源失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"测试所有新闻源失败: {str(e)}") 