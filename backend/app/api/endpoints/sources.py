from typing import Any, List, Dict, Optional
import asyncio
import logging
from datetime import datetime
import time
import traceback

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Path, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_superuser, get_current_active_superuser, get_current_active_user, get_news_source_provider
from app.models.user import User
from app.crud import source as crud
from app.crud.source import (
    get_source, get_sources, create_source, update_source, delete_source,
    get_source_with_stats, create_source_alias, delete_source_alias
)
from app.models.source import SourceType
from app.schemas.source import (
    Source, SourceCreate, SourceUpdate, SourceWithStats,
    SourceAlias, SourceAliasCreate
)
from worker.sources.interface import NewsSourceInterface
from worker.sources.provider import NewsSourceProvider
from worker.stats_wrapper import stats_updater

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("sources_api")

router = APIRouter()

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


# 数据库管理API端点
@router.get("/", response_model=List[Source])
async def read_sources(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    """
    Retrieve sources with pagination.
    """
    sources = get_sources(db, skip=skip, limit=limit)
    processed_sources = []
    
    for source in sources:
        # Convert timedelta fields to integers
        source_dict = {}
        for key, value in source.__dict__.items():
            if key == "_sa_instance_state":
                continue
                
            # Handle timedelta fields
            if key == "update_interval" and hasattr(value, "total_seconds"):
                source_dict[key] = int(value.total_seconds())
            elif key == "cache_ttl" and hasattr(value, "total_seconds"):
                source_dict[key] = int(value.total_seconds())
            else:
                source_dict[key] = value
                
        # Ensure all required fields have valid values
        if "priority" not in source_dict or source_dict["priority"] is None:
            source_dict["priority"] = 0
        if "error_count" not in source_dict or source_dict["error_count"] is None:
            source_dict["error_count"] = 0
        if "news_count" not in source_dict or source_dict["news_count"] is None:
            source_dict["news_count"] = 0
        
        # Convert dictionary to Pydantic model and add to list
        processed_sources.append(Source.model_validate(source_dict))
    
    return processed_sources


@router.post("/", response_model=Source)
def create_new_source(
    *,
    db: Session = Depends(get_db),
    source_in: SourceCreate,
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    创建新闻源
    
    创建新的新闻源配置信息，需要超级用户权限
    """
    source = create_source(db=db, obj_in=source_in)
    return source


@router.get("/available", response_model=List[Dict[str, Any]])
async def read_available_sources(
    source_provider: NewsSourceProvider = Depends(get_news_source_provider),
    db: Session = Depends(get_db)
):
    """
    获取所有可用的新闻源
    """
    # 从提供者获取所有新闻源
    sources = source_provider.get_all_sources()
    
    # 首先收集所有自定义源的ID
    custom_source_ids = [s.source_id for s in sources if s.source_id.startswith('custom-')]
    
    # 如果有自定义源，从数据库获取它们的实际元数据
    custom_source_metadata = {}
    if custom_source_ids:
        try:
            from app.models.source import Source
            from app.models.category import Category
            
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
                
                custom_source_metadata[source.id] = {
                    "name": source.name,
                    "category": category,
                    "country": source.country or "global",
                    "language": source.language or "en",
                    "update_interval": int(update_interval)
                }
        except Exception as e:
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
            })
        else:
            # 使用源对象的元数据
            result.append({
                "source_id": source.source_id,
                "name": source.name,
                "category": source.category,
                "country": getattr(source, "country", ""),
                "language": getattr(source, "language", ""),
                "update_interval": source.update_interval,
            })
    
    return result


@router.get("/external/{source_id}/news", response_model=List[Dict[str, Any]])
async def get_source_news(
    source_id: str,
    force_update: bool = False,
    source_provider: NewsSourceProvider = Depends(get_news_source_provider),
):
    """
    从新闻源获取新闻（外部API调用）
    """
    logger.info(f"开始获取外部新闻源 {source_id} 的新闻, force_update={force_update}")
    
    # 获取新闻源
    source = source_provider.get_source(source_id)
    if not source:
        logger.error(f"新闻源 {source_id} 不存在")
        raise HTTPException(status_code=404, detail=f"新闻源 {source_id} 不存在")
    
    try:
        # 将源的fetch方法包装为external类型
        logger.info(f"将 {source_id} 的fetch方法包装为external类型")
        original_fetch = source.fetch
        source.fetch = lambda *args, **kwargs: stats_updater.wrap_fetch(source_id, original_fetch, api_type="external", *args, **kwargs)
        
        # 获取新闻
        logger.info(f"开始获取 {source_id} 的新闻数据")
        start_time = time.time()
        news_items = await source.get_news(force_update=force_update)
        elapsed_time = time.time() - start_time
        
        # 添加日志以检查返回的类型和数量
        if not news_items:
            logger.warning(f"从 source.get_news 获取到的新闻为空: {news_items}")
            # 尝试直接调用fetch方法获取数据
            logger.info(f"尝试直接调用 fetch 方法获取数据")
            news_items = await source.fetch()
            logger.info(f"直接调用 fetch 获取到 {len(news_items)} 条数据")
            
        logger.info(f"获取 {source_id} 新闻完成，获取到 {len(news_items)} 条数据，耗时 {elapsed_time:.2f}秒")
        
        # 恢复原始fetch方法
        source.fetch = original_fetch
        
        # 检查返回的数据
        if not news_items:
            logger.warning(f"从 {source_id} 获取到的新闻为空列表")
            return []
        
        # 格式化返回数据 - 使用更安全的方法转换成字典
        logger.info(f"开始处理 {len(news_items)} 条新闻数据")
        result = []
        for i, item in enumerate(news_items):
            try:
                # 记录一下第一条和最后一条新闻的详情，用于调试
                if i < 3 or i == len(news_items) - 1:
                    logger.debug(f"新闻项 {i+1}: {getattr(item, 'title', '无标题')}")
                
                # 手动将对象转换为字典，避免序列化问题
                item_dict = {
                    "id": str(item.id),
                    "title": str(item.title),
                    "url": str(item.url),
                    "source_id": str(item.source_id),
                    "source_name": str(item.source_name),
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                    "summary": str(item.summary) if item.summary else "",
                    "content": str(item.content) if hasattr(item, "content") and item.content else "",
                    "country": str(item.country) if hasattr(item, "country") and item.country else "",
                    "language": str(item.language) if hasattr(item, "language") and item.language else "",
                    "category": str(item.category) if hasattr(item, "category") and item.category else "",
                    "extra": {}
                }
                
                # 处理image_url
                if hasattr(item, "image_url") and item.image_url:
                    item_dict["image_url"] = str(item.image_url)
                
                # 安全地处理extra字典
                if hasattr(item, "extra") and item.extra:
                    for k, v in item.extra.items():
                        try:
                            if isinstance(v, (str, int, float, bool, type(None))):
                                item_dict["extra"][k] = v
                            elif isinstance(v, (datetime.datetime, datetime.date)):
                                item_dict["extra"][k] = v.isoformat()
                            else:
                                item_dict["extra"][k] = str(v)
                        except Exception as ex:
                            logger.warning(f"处理extra字段 {k} 时出错: {str(ex)}")
                
                result.append(item_dict)
            except Exception as e:
                logger.error(f"处理第 {i+1} 条新闻项时出错: {str(e)}")
                logger.error(f"错误详情: {traceback.format_exc()}")
        
        logger.info(f"返回 {len(result)} 条新闻数据")
        return result
    except Exception as e:
        logger.error(f"从新闻源 {source_id} 获取新闻时出错: {str(e)}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{source_id}", response_model=Source)
async def read_source(
    source_id: str,
    db: Session = Depends(get_db),
):
    """
    Get a specific source by ID.
    """
    source = get_source(db, source_id)
    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )
    
    # Convert timedelta fields to integers
    source_dict = {}
    for key, value in source.__dict__.items():
        if key == "_sa_instance_state":
            continue
            
        # Handle timedelta fields
        if key == "update_interval" and hasattr(value, "total_seconds"):
            source_dict[key] = int(value.total_seconds())
        elif key == "cache_ttl" and hasattr(value, "total_seconds"):
            source_dict[key] = int(value.total_seconds())
        else:
            source_dict[key] = value
            
    # Ensure all required fields have valid values
    if "priority" not in source_dict or source_dict["priority"] is None:
        source_dict["priority"] = 0
    if "error_count" not in source_dict or source_dict["error_count"] is None:
        source_dict["error_count"] = 0
    if "news_count" not in source_dict or source_dict["news_count"] is None:
        source_dict["news_count"] = 0
    
    # Convert dictionary to Pydantic model
    return Source.model_validate(source_dict)


@router.put("/{source_id}", response_model=Source)
async def update_source_api(
    source_id: str,
    source_in: SourceUpdate,
    db: Session = Depends(get_db),
):
    """
    Update a source.
    """
    source = get_source(db, source_id)
    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )
    source = update_source(db, db_obj=source, obj_in=source_in)
    
    # Convert timedelta fields to integers for response validation
    source_dict = {}
    for key, value in source.__dict__.items():
        if key == "_sa_instance_state":
            continue
            
        # Handle timedelta fields
        if key == "update_interval" and hasattr(value, "total_seconds"):
            source_dict[key] = int(value.total_seconds())
        elif key == "cache_ttl" and hasattr(value, "total_seconds"):
            source_dict[key] = int(value.total_seconds())
        else:
            source_dict[key] = value
            
    # Ensure all required fields have valid values
    if "priority" not in source_dict or source_dict["priority"] is None:
        source_dict["priority"] = 0
    if "error_count" not in source_dict or source_dict["error_count"] is None:
        source_dict["error_count"] = 0
    if "news_count" not in source_dict or source_dict["news_count"] is None:
        source_dict["news_count"] = 0
    
    # Convert dictionary to Pydantic model
    return Source.model_validate(source_dict)


@router.delete("/{source_id}", response_model=bool)
def delete_source_api(
    *,
    db: Session = Depends(get_db),
    source_id: str = Path(..., description="The ID of the source to delete"),
) -> Any:
    """
    删除新闻源
    
    删除指定的新闻源配置
    """
    source = get_source(db=db, source_id=source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    delete_source(db=db, source_id=source_id)
    return True


@router.get("/{source_id}/stats", response_model=SourceWithStats)
async def read_source_stats(
    source_id: str,
    db: Session = Depends(get_db),
):
    """
    Get source with news statistics.
    """
    source = crud.get_source_with_stats(db, source_id=source_id)
    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )

    # Convert the source object to a dictionary
    source_dict = {}
    for key, value in source.__dict__.items():
        if key == "_sa_instance_state":
            continue
            
        # Handle timedelta fields
        if key == "update_interval" and hasattr(value, "total_seconds"):
            source_dict[key] = int(value.total_seconds())
        elif key == "cache_ttl" and hasattr(value, "total_seconds"):
            source_dict[key] = int(value.total_seconds())
        else:
            source_dict[key] = value
    
    # Ensure all required fields have valid values
    if "priority" not in source_dict or source_dict["priority"] is None:
        source_dict["priority"] = 0
    if "error_count" not in source_dict or source_dict["error_count"] is None:
        source_dict["error_count"] = 0
    if "news_count" not in source_dict or source_dict["news_count"] is None:
        source_dict["news_count"] = 0
    
    # Convert dictionary to Pydantic model
    return SourceWithStats.model_validate(source_dict)


@router.post("/aliases", response_model=SourceAlias)
def create_source_alias_api(
    *,
    db: Session = Depends(get_db),
    alias_in: SourceAliasCreate,
) -> Any:
    """
    创建新闻源别名
    
    为新闻源创建一个别名，可用于URL简化
    """
    source = get_source(db=db, source_id=alias_in.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    alias = create_source_alias(db=db, alias=alias_in.alias, source_id=alias_in.source_id)
    return alias


@router.delete("/aliases/{alias}", response_model=bool)
def delete_source_alias_api(
    *,
    db: Session = Depends(get_db),
    alias: str = Path(..., description="The alias to delete"),
) -> Any:
    """
    删除新闻源别名
    
    删除指定的新闻源别名
    """
    result = delete_source_alias(db=db, alias=alias)
    if not result:
        raise HTTPException(status_code=404, detail="Alias not found")
    return True 