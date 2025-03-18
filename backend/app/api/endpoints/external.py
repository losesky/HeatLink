from typing import Any, List, Dict, Optional
import asyncio
import logging
from datetime import datetime
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Path
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


# 辅助函数
async def close_source(source):
    """关闭新闻源并释放资源"""
    if source is None:
        return
    
    try:
        # 调用close方法
        if hasattr(source, 'close'):
            try:
                await source.close()
                return
            except Exception as e:
                logger.warning(f"Error calling close() method: {str(e)}")
        
        # 尝试关闭http_client
        if hasattr(source, '_http_client') and source._http_client is not None:
            if hasattr(source._http_client, 'close'):
                await source._http_client.close()
        
        # 尝试关闭aiohttp会话
        import aiohttp
        import inspect
        for attr_name in dir(source):
            if attr_name.startswith('_'):
                continue
                
            try:
                attr = getattr(source.__class__, attr_name, None)
                if attr and (inspect.iscoroutine(attr) or inspect.isawaitable(attr) or 
                           inspect.iscoroutinefunction(attr) or isinstance(attr, property)):
                    continue
                
                attr = getattr(source, attr_name)
                
                if isinstance(attr, aiohttp.ClientSession) and not attr.closed:
                    await attr.close()
            except (AttributeError, TypeError):
                pass
    except Exception as e:
        logger.warning(f"Error closing source: {str(e)}")


async def fetch_source_news(source_type: str, timeout: int = 60) -> Dict[str, Any]:
    """获取指定新闻源的新闻"""
    result = {
        "source": None,
        "news": [],
        "news_count": 0,
        "fetch_time": 0,
        "error": None
    }
    
    logger.info(f"Fetching news from source: {source_type}")
    
    source = None
    try:
        source = NewsSourceFactory.create_source(source_type)
        
        # 获取源信息
        result["source"] = {
            "source_id": source.source_id,
            "name": source.name,
            "category": source.category,
            "country": source.country,
            "language": source.language,
            "update_interval": source.update_interval if isinstance(source.update_interval, int) else int(source.update_interval.total_seconds()) if hasattr(source.update_interval, 'total_seconds') else None,
            "cache_ttl": source.cache_ttl if isinstance(source.cache_ttl, int) else int(source.cache_ttl.total_seconds()) if hasattr(source.cache_ttl, 'total_seconds') else None,
            "description": getattr(source, 'description', None)
        }
        
        # 获取新闻
        start_time = time.time()
        try:
            fetch_task = asyncio.create_task(source.fetch())
            news_items = await asyncio.wait_for(fetch_task, timeout=timeout)
            elapsed_time = time.time() - start_time
            
            # 记录结果
            result["news"] = [item.to_dict() for item in news_items]
            result["news_count"] = len(news_items)
            result["fetch_time"] = elapsed_time
            
            logger.info(f"Fetch successful: {len(news_items)} items in {elapsed_time:.2f}s")
        except asyncio.TimeoutError:
            elapsed_time = time.time() - start_time
            error_msg = f"Timeout after {elapsed_time:.2f}s"
            result["error"] = error_msg
            logger.error(error_msg)
        except Exception as e:
            elapsed_time = time.time() - start_time
            error_msg = f"Error fetching data: {str(e)}"
            result["error"] = error_msg
            logger.error(error_msg)
    except Exception as e:
        error_msg = f"Error creating source: {str(e)}"
        result["error"] = error_msg
        logger.error(error_msg)
    finally:
        # 关闭新闻源
        if source:
            await close_source(source)
    
    return result


# API端点
@router.get("/sources", response_model=SourcesResponse)
async def get_sources():
    """
    获取所有可用的新闻源
    
    返回所有可用的新闻源及其基本信息
    """
    # 获取所有默认新闻源
    sources = NewsSourceFactory.create_default_sources()
    
    # 构建响应
    source_info_list = []
    for source in sources:
        source_info = {
            "source_id": source.source_id,
            "name": source.name,
            "category": source.category,
            "country": source.country,
            "language": source.language,
            "update_interval": source.update_interval if isinstance(source.update_interval, int) else int(source.update_interval.total_seconds()) if hasattr(source.update_interval, 'total_seconds') else None,
            "cache_ttl": source.cache_ttl if isinstance(source.cache_ttl, int) else int(source.cache_ttl.total_seconds()) if hasattr(source.cache_ttl, 'total_seconds') else None,
            "description": getattr(source, 'description', None)
        }
        source_info_list.append(source_info)
    
    # 关闭所有新闻源
    for source in sources:
        await close_source(source)
    
    return {
        "total_sources": len(source_info_list),
        "sources": sorted(source_info_list, key=lambda x: x["source_id"])
    }


@router.get("/source/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: str = Path(..., description="新闻源ID"),
    timeout: int = Query(60, description="获取超时时间（秒）"),
):
    """
    获取指定新闻源的新闻
    
    - **source_id**: 新闻源ID
    - **timeout**: 获取超时时间（秒）
    """
    result = await fetch_source_news(source_id, timeout)
    
    if result["error"]:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching news from {source_id}: {result['error']}"
        )
    
    return {
        "source": result["source"],
        "news_count": result["news_count"],
        "news": result["news"],
        "fetch_time": result["fetch_time"]
    }


@router.get("/all", response_model=AllSourcesResponse)
async def get_all_sources(
    background_tasks: BackgroundTasks,
    timeout: int = Query(60, description="获取超时时间（秒）"),
    max_concurrent: int = Query(5, description="最大并发数"),
    category: Optional[str] = Query(None, description="按分类筛选"),
    country: Optional[str] = Query(None, description="按国家筛选"),
    language: Optional[str] = Query(None, description="按语言筛选")
):
    """
    获取所有新闻源的新闻
    
    - **timeout**: 获取超时时间（秒）
    - **max_concurrent**: 最大并发数
    - **category**: 按分类筛选
    - **country**: 按国家筛选
    - **language**: 按语言筛选
    """
    start_time = datetime.now()
    
    # 获取所有默认新闻源
    sources = NewsSourceFactory.create_default_sources()
    
    # 应用筛选
    if category:
        sources = [s for s in sources if s.category == category]
    if country:
        sources = [s for s in sources if s.country == country]
    if language:
        sources = [s for s in sources if s.language == language]
    
    source_ids = [source.source_id for source in sources]
    
    # 关闭所有新闻源
    for source in sources:
        await close_source(source)
    
    logger.info(f"Fetching news from {len(source_ids)} sources...")
    
    # 创建信号量限制并发
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_with_semaphore(source_id: str) -> Dict[str, Any]:
        async with semaphore:
            result = await fetch_source_news(source_id, timeout=timeout)
            return result
    
    # 创建所有获取任务
    tasks = [fetch_with_semaphore(source_id) for source_id in source_ids]
    
    # 执行所有任务
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理结果
    successful_sources = []
    failed_sources = []
    all_news = []
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Task error for {source_ids[i]}: {str(result)}")
            failed_sources.append({
                "source_id": source_ids[i],
                "error": str(result)
            })
            continue
        
        if result["error"] is None:
            successful_sources.append({
                "source_id": result["source"]["source_id"],
                "name": result["source"]["name"],
                "category": result["source"]["category"],
                "news_count": result["news_count"],
                "fetch_time": result["fetch_time"]
            })
            all_news.extend(result["news"])
        else:
            failed_sources.append({
                "source_id": source_ids[i],
                "error": result["error"]
            })
    
    end_time = datetime.now()
    total_time = (end_time - start_time).total_seconds()
    
    # 关闭http_client单例
    async def cleanup():
        from worker.utils.http_client import http_client
        await http_client.close()
    
    # 添加清理任务到后台任务
    background_tasks.add_task(cleanup)
    
    return {
        "summary": {
            "total_sources": len(source_ids),
            "successful_sources": len(successful_sources),
            "failed_sources": len(failed_sources),
            "success_rate": f"{len(successful_sources) / len(source_ids) * 100:.1f}%",
            "total_time": f"{total_time:.2f}s",
            "total_news": len(all_news)
        },
        "successful_sources": sorted(successful_sources, key=lambda x: x["source_id"]),
        "failed_sources": sorted(failed_sources, key=lambda x: x["source_id"]),
        "news": all_news
    }


@router.get("/sample/{source_id}", response_model=List[NewsItem])
async def get_source_sample(
    source_id: str = Path(..., description="新闻源ID"),
    limit: int = Query(5, description="返回的新闻数量"),
    timeout: int = Query(60, description="获取超时时间（秒）")
):
    """
    获取指定新闻源的样本数据
    
    - **source_id**: 新闻源ID
    - **limit**: 返回的新闻数量
    - **timeout**: 获取超时时间（秒）
    """
    # 创建新闻源
    source = None
    try:
        source = NewsSourceFactory.create_source(source_id)
        
        # 获取数据
        fetch_task = asyncio.create_task(source.fetch())
        news_items = await asyncio.wait_for(fetch_task, timeout=timeout)
        
        # 限制返回数量
        limited_items = news_items[:limit]
        
        # 转换为字典
        result = [item.to_dict() for item in limited_items]
        
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching sample data: {str(e)}"
        )
    finally:
        # 关闭新闻源
        if source:
            await close_source(source)


@router.get("/compare", response_model=SourceComparisonResponse)
async def compare_sources(
    sources: str = Query(..., description="要比较的新闻源ID，用逗号分隔"),
    timeout: int = Query(60, description="获取超时时间（秒）")
):
    """
    比较多个新闻源的数据格式
    
    - **sources**: 要比较的新闻源ID，用逗号分隔
    - **timeout**: 获取超时时间（秒）
    """
    source_list = [s.strip() for s in sources.split(",")]
    if not source_list:
        raise HTTPException(
            status_code=400,
            detail="未指定新闻源"
        )
    
    result = {}
    
    for source_id in source_list:
        try:
            # 获取样本数据
            sample = await get_source_sample(source_id, limit=1, timeout=timeout)
            
            if not sample:
                result[source_id] = {"error": "未返回数据"}
                continue
            
            # 分析字段和类型
            fields = {}
            for key, value in sample[0].items():
                if value is not None:
                    field_type = type(value).__name__
                    fields[key] = field_type
            
            result[source_id] = {
                "fields": fields,
                "sample": sample[0]
            }
        except Exception as e:
            result[source_id] = {"error": str(e)}
    
    return {"sources": result}


@router.get("/stats", response_model=SourcesStatsResponse)
async def get_sources_stats():
    """
    获取所有新闻源的统计信息
    
    返回所有新闻源的统计信息，包括分类、国家、语言等
    """
    # 获取所有默认新闻源
    sources = NewsSourceFactory.create_default_sources()
    
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
    
    # 构建源统计
    source_stats = []
    for source in sources:
        source_stats.append({
            "source_id": source.source_id,
            "name": source.name,
            "category": source.category,
            "country": source.country,
            "language": source.language,
            "update_interval": source.update_interval if isinstance(source.update_interval, int) else int(source.update_interval.total_seconds()) if hasattr(source.update_interval, 'total_seconds') else None,
            "cache_ttl": source.cache_ttl if isinstance(source.cache_ttl, int) else int(source.cache_ttl.total_seconds()) if hasattr(source.cache_ttl, 'total_seconds') else None
        })
    
    # 关闭所有新闻源
    for source in sources:
        await close_source(source)
    
    return {
        "total_sources": len(sources),
        "categories": categories,
        "countries": countries,
        "languages": languages,
        "sources": sorted(source_stats, key=lambda x: x["source_id"])
    }


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
    获取统一格式的新闻数据
    
    - **page**: 页码，从1开始
    - **page_size**: 每页数量
    - **category**: 按分类筛选
    - **country**: 按国家筛选
    - **language**: 按语言筛选
    - **source_id**: 按新闻源ID筛选
    - **keyword**: 按关键词筛选
    - **sort_by**: 排序字段，支持published_at、title
    - **sort_order**: 排序方向，支持asc、desc
    - **timeout**: 获取超时时间（秒）
    - **max_concurrent**: 最大并发数
    """
    # 获取所有默认新闻源
    sources = NewsSourceFactory.create_default_sources()
    
    # 应用筛选
    if category:
        sources = [s for s in sources if s.category == category]
    if country:
        sources = [s for s in sources if s.country == country]
    if language:
        sources = [s for s in sources if s.language == language]
    if source_id:
        sources = [s for s in sources if s.source_id == source_id]
    
    source_ids = [source.source_id for source in sources]
    
    # 关闭所有新闻源
    for source in sources:
        await close_source(source)
    
    if not source_ids:
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "news": [],
            "filters": {
                "category": category,
                "country": country,
                "language": language,
                "source_id": source_id,
                "keyword": keyword,
                "sort_by": sort_by,
                "sort_order": sort_order
            }
        }
    
    logger.info(f"Fetching unified news from {len(source_ids)} sources...")
    
    # 创建信号量限制并发
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_with_semaphore(source_id: str) -> Dict[str, Any]:
        async with semaphore:
            result = await fetch_source_news(source_id, timeout=timeout)
            return result
    
    # 创建所有获取任务
    tasks = [fetch_with_semaphore(source_id) for source_id in source_ids]
    
    # 执行所有任务
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理结果
    all_news = []
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Task error for {source_ids[i]}: {str(result)}")
            continue
        
        if result["error"] is None and result["news"]:
            # 转换为统一格式
            for item in result["news"]:
                # 确保所有必要字段都存在
                if "id" not in item or "title" not in item or "url" not in item:
                    continue
                
                unified_item = {
                    "id": item["id"],
                    "title": item["title"],
                    "url": item["url"],
                    "source_id": result["source"]["source_id"],
                    "source_name": result["source"]["name"],
                    "category": result["source"]["category"],
                    "published_at": item.get("published_at"),
                    "summary": item.get("summary"),
                    "content": item.get("content"),
                    "image_url": item.get("image_url"),
                    "country": result["source"]["country"],
                    "language": result["source"]["language"]
                }
                all_news.append(unified_item)
    
    # 应用关键词筛选
    if keyword:
        keyword = keyword.lower()
        filtered_news = []
        for item in all_news:
            if (keyword in item["title"].lower() or 
                (item["summary"] and keyword in item["summary"].lower()) or
                (item["content"] and keyword in item["content"].lower())):
                filtered_news.append(item)
        all_news = filtered_news
    
    # 排序
    if sort_by == "published_at":
        # 处理可能的None值
        def get_published_at(item):
            if not item["published_at"]:
                return datetime.min if sort_order == "desc" else datetime.max
            try:
                return datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return datetime.min if sort_order == "desc" else datetime.max
        
        all_news.sort(key=get_published_at, reverse=(sort_order == "desc"))
    elif sort_by == "title":
        all_news.sort(key=lambda x: x["title"], reverse=(sort_order == "desc"))
    
    # 计算分页
    total = len(all_news)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total)
    
    # 获取当前页的新闻
    paged_news = all_news[start_idx:end_idx] if start_idx < total else []
    
    # 关闭http_client单例
    async def cleanup():
        from worker.utils.http_client import http_client
        await http_client.close()
    
    # 添加清理任务到后台任务
    background_tasks.add_task(cleanup)
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "news": paged_news,
        "filters": {
            "category": category,
            "country": country,
            "language": language,
            "source_id": source_id,
            "keyword": keyword,
            "sort_by": sort_by,
            "sort_order": sort_order
        }
    }


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
    获取热门新闻和推荐新闻
    
    - **hot_limit**: 热门新闻数量
    - **recommended_limit**: 推荐新闻数量
    - **category_limit**: 每个分类的新闻数量
    - **timeout**: 获取超时时间（秒）
    - **force_update**: 是否强制更新
    """
    # 更新聚合器
    await aggregator_manager.update(force=force_update)
    
    # 获取热门话题
    hot_topics = aggregator_manager.get_hot_topics(limit=hot_limit)
    
    # 转换为统一格式
    hot_news = []
    for topic in hot_topics:
        main_news = topic.get("main_news", {})
        if not main_news:
            continue
        
        hot_news.append({
            "id": main_news.get("id", ""),
            "title": main_news.get("title", ""),
            "url": main_news.get("url", ""),
            "source_id": main_news.get("source_id", ""),
            "source_name": main_news.get("source_name", ""),
            "category": main_news.get("category", ""),
            "published_at": main_news.get("published_at"),
            "summary": main_news.get("summary"),
            "content": main_news.get("content"),
            "image_url": main_news.get("image_url"),
            "country": main_news.get("country"),
            "language": main_news.get("language")
        })
    
    # 获取所有新闻源
    sources = NewsSourceFactory.create_default_sources()
    
    # 按分类分组
    categories = {}
    for source in sources:
        if source.category not in categories:
            categories[source.category] = []
        categories[source.category].append(source.source_id)
    
    # 关闭所有新闻源
    for source in sources:
        await close_source(source)
    
    # 获取每个分类的新闻
    category_news = {}
    for category, source_ids in categories.items():
        if not source_ids:
            continue
        
        # 只取第一个源获取新闻
        source_id = source_ids[0]
        try:
            result = await fetch_source_news(source_id, timeout=timeout)
            if result["error"] is None and result["news"]:
                # 转换为统一格式
                category_items = []
                for item in result["news"][:category_limit]:
                    # 确保所有必要字段都存在
                    if "id" not in item or "title" not in item or "url" not in item:
                        continue
                    
                    unified_item = {
                        "id": item["id"],
                        "title": item["title"],
                        "url": item["url"],
                        "source_id": result["source"]["source_id"],
                        "source_name": result["source"]["name"],
                        "category": result["source"]["category"],
                        "published_at": item.get("published_at"),
                        "summary": item.get("summary"),
                        "content": item.get("content"),
                        "image_url": item.get("image_url"),
                        "country": result["source"]["country"],
                        "language": result["source"]["language"]
                    }
                    category_items.append(unified_item)
                
                if category_items:
                    category_news[category] = category_items
        except Exception as e:
            logger.error(f"Error fetching news for category {category}: {str(e)}")
    
    # 获取推荐新闻（从所有新闻中随机选择）
    all_news = []
    for items in category_news.values():
        all_news.extend(items)
    
    import random
    recommended_news = []
    if all_news:
        # 随机选择推荐新闻
        sample_size = min(recommended_limit, len(all_news))
        recommended_news = random.sample(all_news, sample_size)
    
    # 关闭http_client单例
    async def cleanup():
        from worker.utils.http_client import http_client
        await http_client.close()
    
    # 添加清理任务到后台任务
    background_tasks.add_task(cleanup)
    
    return {
        "hot_news": hot_news,
        "recommended_news": recommended_news,
        "categories": category_news
    }


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
    
    - **query**: 搜索关键词
    - **page**: 页码，从1开始
    - **page_size**: 每页数量
    - **category**: 按分类筛选
    - **country**: 按国家筛选
    - **language**: 按语言筛选
    - **source_id**: 按新闻源ID筛选
    - **max_results**: 最大返回结果数
    """
    # 获取所有新闻源
    sources = source_manager.get_all_sources()
    
    # 应用筛选
    if category:
        sources = [s for s in sources if s.category == category]
    if country:
        sources = [s for s in sources if s.country == country]
    if language:
        sources = [s for s in sources if s.language == language]
    if source_id:
        sources = [s for s in sources if s.source_id == source_id]
    
    # 如果没有符合条件的源，返回空结果
    if not sources:
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "query": query,
            "results": []
        }
    
    # 搜索新闻
    results = await source_manager.search_news(query, max_results=max_results)
    
    # 过滤结果
    filtered_results = []
    for item in results:
        # 检查是否符合筛选条件
        if category and item.category != category:
            continue
        if country and item.country != country:
            continue
        if language and item.language != language:
            continue
        if source_id and item.source_id != source_id:
            continue
        
        # 转换为统一格式
        unified_item = {
            "id": item.id,
            "title": item.title,
            "url": item.url,
            "source_id": item.source_id,
            "source_name": item.source_name,
            "category": item.category,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "summary": item.summary,
            "content": item.content,
            "image_url": item.image_url,
            "country": item.country,
            "language": item.language
        }
        filtered_results.append(unified_item)
    
    # 计算分页
    total = len(filtered_results)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total)
    
    # 获取当前页的结果
    paged_results = filtered_results[start_idx:end_idx] if start_idx < total else []
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "query": query,
        "results": paged_results
    } 