from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path
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

router = APIRouter()


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