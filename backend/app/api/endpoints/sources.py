from typing import Any, List, Dict, Optional
import asyncio
import logging
from datetime import datetime
import time

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
):
    """
    获取所有可用的新闻源
    """
    # 从提供者获取所有新闻源
    sources = source_provider.get_all_sources()
    
    # 格式化返回数据
    result = []
    for source in sources:
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
    从新闻源获取新闻
    """
    # 获取新闻源
    source = source_provider.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"新闻源 {source_id} 不存在")
    
    try:
        # 获取新闻
        news_items = await source.get_news(force_update=force_update)
        
        # 格式化返回数据
        result = []
        for item in news_items:
            result.append(item.to_dict())
        
        return result
    except Exception as e:
        logger.error(f"从新闻源 {source_id} 获取新闻时出错: {str(e)}")
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
    current_user: User = Depends(get_current_active_superuser),
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
    return source


@router.delete("/{source_id}", response_model=bool)
def delete_source_api(
    *,
    db: Session = Depends(get_db),
    source_id: str = Path(..., description="The ID of the source to delete"),
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    删除新闻源
    
    删除指定的新闻源配置，需要超级用户权限
    """
    source = get_source(db=db, id=source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    delete_source(db=db, id=source_id)
    return True


@router.get("/{source_id}/stats", response_model=SourceWithStats)
async def read_source_stats(
    source_id: str,
    db: Session = Depends(get_db),
):
    """
    Get source with news statistics.
    """
    source = crud.get_source_with_stats(db, id=source_id)
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
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    创建新闻源别名
    
    为新闻源创建一个别名，可用于URL简化，需要超级用户权限
    """
    source = get_source(db=db, id=alias_in.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    alias = create_source_alias(db=db, obj_in=alias_in)
    return alias


@router.delete("/aliases/{alias}", response_model=bool)
def delete_source_alias_api(
    *,
    db: Session = Depends(get_db),
    alias: str = Path(..., description="The alias to delete"),
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    删除新闻源别名
    
    删除指定的新闻源别名，需要超级用户权限
    """
    result = delete_source_alias(db=db, alias=alias)
    if not result:
        raise HTTPException(status_code=404, detail="Alias not found")
    return True 