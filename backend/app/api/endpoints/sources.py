from typing import Any, List, Dict, Optional
import asyncio
import logging
from datetime import datetime
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Path, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_superuser
from app.crud.source import (
    get_source, get_sources, create_source, update_source, delete_source,
    get_source_with_stats, create_source_alias, delete_source_alias
)
from app.models.source import SourceType
from app.schemas.source import (
    Source, SourceCreate, SourceUpdate, SourceWithStats,
    SourceAlias, SourceAliasCreate
)
from worker.sources.factory import NewsSourceFactory
from worker.sources.base import NewsSource, NewsItemModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("sources_api")

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
@router.get("/available", response_model=SourcesResponse)
async def get_available_sources() -> Any:
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


@router.get("/fetch/{source_id}", response_model=SourceResponse)
async def fetch_source(
    source_id: str = Path(..., description="新闻源ID"),
    timeout: int = Query(60, description="获取超时时间（秒）"),
) -> Any:
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


@router.get("/fetch-all", response_model=Dict[str, Any])
async def fetch_all_sources(
    background_tasks: BackgroundTasks,
    timeout: int = Query(60, description="获取超时时间（秒）"),
    max_concurrent: int = Query(5, description="最大并发数"),
    category: Optional[str] = Query(None, description="按分类筛选"),
    country: Optional[str] = Query(None, description="按国家筛选"),
    language: Optional[str] = Query(None, description="按语言筛选")
) -> Any:
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
) -> Any:
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
) -> Any:
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
async def get_sources_stats() -> Any:
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


@router.get("/", response_model=List[Source])
def read_sources(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    active_only: Optional[bool] = None,
    type_filter: Optional[SourceType] = None,
    category_id: Optional[int] = None,
    country: Optional[str] = None,
    language: Optional[str] = None,
) -> Any:
    """
    Retrieve sources.
    """
    sources = get_sources(
        db, 
        skip=skip, 
        limit=limit, 
        active_only=active_only,
        type_filter=type_filter,
        category_id=category_id,
        country=country,
        language=language
    )
    
    # 转换 timedelta 为整数（秒数）
    for source in sources:
        if hasattr(source, 'update_interval') and hasattr(source.update_interval, 'total_seconds'):
            source.update_interval = int(source.update_interval.total_seconds())
        if hasattr(source, 'cache_ttl') and hasattr(source.cache_ttl, 'total_seconds'):
            source.cache_ttl = int(source.cache_ttl.total_seconds())
    
    return sources


@router.post("/", response_model=Source)
def create_new_source(
    *,
    db: Session = Depends(get_db),
    source_in: SourceCreate,
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Create new source.
    """
    source = get_source(db, source_id=source_in.id)
    if source:
        raise HTTPException(
            status_code=400,
            detail=f"Source with ID {source_in.id} already exists",
        )
    source = create_source(db, source_in)
    
    # 转换 timedelta 为整数（秒数）
    if hasattr(source, 'update_interval') and hasattr(source.update_interval, 'total_seconds'):
        source.update_interval = int(source.update_interval.total_seconds())
    if hasattr(source, 'cache_ttl') and hasattr(source.cache_ttl, 'total_seconds'):
        source.cache_ttl = int(source.cache_ttl.total_seconds())
    
    return source


@router.get("/{source_id}", response_model=Source)
def read_source(
    *,
    db: Session = Depends(get_db),
    source_id: str = Path(..., description="The ID of the source to get"),
) -> Any:
    """
    Get source by ID.
    """
    source = get_source(db, source_id=source_id)
    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )
    
    # 转换 timedelta 为整数（秒数）
    if hasattr(source, 'update_interval') and hasattr(source.update_interval, 'total_seconds'):
        source.update_interval = int(source.update_interval.total_seconds())
    if hasattr(source, 'cache_ttl') and hasattr(source.cache_ttl, 'total_seconds'):
        source.cache_ttl = int(source.cache_ttl.total_seconds())
    
    return source


@router.put("/{source_id}", response_model=Source)
def update_source_api(
    *,
    db: Session = Depends(get_db),
    source_id: str = Path(..., description="The ID of the source to update"),
    source_in: SourceUpdate,
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Update a source.
    """
    source = get_source(db, source_id=source_id)
    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )
    source = update_source(db, source_id=source_id, source=source_in)
    
    # 转换 timedelta 为整数（秒数）
    if hasattr(source, 'update_interval') and hasattr(source.update_interval, 'total_seconds'):
        source.update_interval = int(source.update_interval.total_seconds())
    if hasattr(source, 'cache_ttl') and hasattr(source.cache_ttl, 'total_seconds'):
        source.cache_ttl = int(source.cache_ttl.total_seconds())
    
    return source


@router.delete("/{source_id}", response_model=bool)
def delete_source_api(
    *,
    db: Session = Depends(get_db),
    source_id: str = Path(..., description="The ID of the source to delete"),
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Delete a source.
    """
    source = get_source(db, source_id=source_id)
    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )
    result = delete_source(db, source_id=source_id)
    return result


@router.get("/{source_id}/stats", response_model=SourceWithStats)
def read_source_stats(
    *,
    db: Session = Depends(get_db),
    source_id: str = Path(..., description="The ID of the source to get stats for"),
) -> Any:
    """
    Get source statistics.
    """
    result = get_source_with_stats(db, source_id=source_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )
    
    source_data = {
        **result["source"].__dict__,
        "news_count": result["news_count"],
        "latest_news_time": result["latest_news_time"]
    }
    
    # Remove SQLAlchemy state
    if "_sa_instance_state" in source_data:
        del source_data["_sa_instance_state"]
    
    # 转换 timedelta 为整数（秒数）
    if "update_interval" in source_data and hasattr(source_data["update_interval"], "total_seconds"):
        source_data["update_interval"] = int(source_data["update_interval"].total_seconds())
    if "cache_ttl" in source_data and hasattr(source_data["cache_ttl"], "total_seconds"):
        source_data["cache_ttl"] = int(source_data["cache_ttl"].total_seconds())
    
    return source_data


@router.post("/aliases", response_model=SourceAlias)
def create_source_alias_api(
    *,
    db: Session = Depends(get_db),
    alias_in: SourceAliasCreate,
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Create a source alias.
    """
    source = get_source(db, source_id=alias_in.source_id)
    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )
    
    alias = create_source_alias(db, alias=alias_in.alias, source_id=alias_in.source_id)
    if not alias:
        raise HTTPException(
            status_code=400,
            detail="Could not create alias",
        )
    
    return alias


@router.delete("/aliases/{alias}", response_model=bool)
def delete_source_alias_api(
    *,
    db: Session = Depends(get_db),
    alias: str = Path(..., description="The alias to delete"),
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Delete a source alias.
    """
    result = delete_source_alias(db, alias=alias)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Alias not found",
        )
    
    return result 