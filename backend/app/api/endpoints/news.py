from typing import Any, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_superuser, get_current_active_user
from app.crud.news import (
    get_news_by_id, get_news, get_news_with_relations,
    get_news_list_items, create_news, update_news, delete_news,
    increment_view_count, get_trending_news,
    add_tag_to_news, remove_tag_from_news,
    update_news_cluster, get_news_by_cluster
)
from app.crud.user import add_read_history
from app.models.user import User
from app.schemas.news import (
    News, NewsCreate, NewsUpdate, NewsWithRelations, NewsListItem
)

router = APIRouter()


@router.get("/", response_model=List[NewsListItem])
def read_news(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 20,
    source_id: Optional[str] = None,
    category_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    search: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    is_top: Optional[bool] = None,
) -> Any:
    """
    Retrieve news.
    """
    news = get_news_list_items(
        db,
        skip=skip,
        limit=limit,
        source_id=source_id,
        category_id=category_id,
        tag_id=tag_id,
        search_query=search,
        start_date=start_date,
        end_date=end_date,
        is_top=is_top
    )
    return news


@router.post("/", response_model=News)
def create_news_item(
    *,
    db: Session = Depends(get_db),
    news_in: NewsCreate,
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Create new news item.
    """
    news = create_news(db, news_in)
    return news


@router.get("/trending", response_model=List[NewsListItem])
def read_trending_news(
    db: Session = Depends(get_db),
    limit: int = 10,
    hours: int = 24,
    category_id: Optional[int] = None,
) -> Any:
    """
    Retrieve trending news.
    """
    news = get_trending_news(
        db,
        limit=limit,
        hours=hours,
        category_id=category_id
    )
    return news


@router.get("/cluster/{cluster_id}", response_model=List[NewsListItem])
def read_news_by_cluster(
    *,
    db: Session = Depends(get_db),
    cluster_id: str = Path(..., description="The cluster ID"),
    limit: int = 20,
) -> Any:
    """
    Retrieve news by cluster.
    """
    news = get_news_by_cluster(db, cluster_id=cluster_id, limit=limit)
    return news


@router.get("/{news_id}", response_model=NewsWithRelations)
def read_news_item(
    *,
    db: Session = Depends(get_db),
    news_id: int = Path(..., description="The ID of the news to get"),
    current_user: Optional[User] = Depends(get_current_active_user),
) -> Any:
    """
    Get news by ID.
    """
    result = get_news_with_relations(db, news_id=news_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="News not found",
        )
    
    # Increment view count
    increment_view_count(db, news_id=news_id)
    
    # Add to read history if user is logged in
    if current_user:
        add_read_history(db, user_id=current_user.id, news_id=news_id)
    
    # Prepare response
    news = result["news"]
    source = result["source"]
    category = result["category"]
    tags = result["tags"]
    
    response = {
        **news.__dict__,
        "source_name": source.name if source else "",
        "category_name": category.name if category else None,
        "tags": [tag.name for tag in tags]
    }
    
    # Remove SQLAlchemy state
    if "_sa_instance_state" in response:
        del response["_sa_instance_state"]
    
    return response


@router.put("/{news_id}", response_model=News)
def update_news_item(
    *,
    db: Session = Depends(get_db),
    news_id: int = Path(..., description="The ID of the news to update"),
    news_in: NewsUpdate,
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Update a news item.
    """
    news = get_news_by_id(db, news_id=news_id)
    if not news:
        raise HTTPException(
            status_code=404,
            detail="News not found",
        )
    news = update_news(db, news_id=news_id, news=news_in)
    return news


@router.delete("/{news_id}", response_model=bool)
def delete_news_item(
    *,
    db: Session = Depends(get_db),
    news_id: int = Path(..., description="The ID of the news to delete"),
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Delete a news item.
    """
    news = get_news_by_id(db, news_id=news_id)
    if not news:
        raise HTTPException(
            status_code=404,
            detail="News not found",
        )
    result = delete_news(db, news_id=news_id)
    return result


@router.post("/{news_id}/tags/{tag_id}", response_model=bool)
def add_tag(
    *,
    db: Session = Depends(get_db),
    news_id: int = Path(..., description="The ID of the news"),
    tag_id: int = Path(..., description="The ID of the tag"),
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Add a tag to a news item.
    """
    result = add_tag_to_news(db, news_id=news_id, tag_id=tag_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="News or tag not found",
        )
    return result


@router.delete("/{news_id}/tags/{tag_id}", response_model=bool)
def remove_tag(
    *,
    db: Session = Depends(get_db),
    news_id: int = Path(..., description="The ID of the news"),
    tag_id: int = Path(..., description="The ID of the tag"),
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Remove a tag from a news item.
    """
    result = remove_tag_from_news(db, news_id=news_id, tag_id=tag_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="News or tag not found",
        )
    return result


@router.put("/{news_id}/cluster/{cluster_id}", response_model=News)
def set_news_cluster(
    *,
    db: Session = Depends(get_db),
    news_id: int = Path(..., description="The ID of the news"),
    cluster_id: str = Path(..., description="The cluster ID"),
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Set the cluster for a news item.
    """
    news = update_news_cluster(db, news_id=news_id, cluster_id=cluster_id)
    if not news:
        raise HTTPException(
            status_code=404,
            detail="News not found",
        )
    return news 