from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func, and_, or_

from app.models.news import News
from app.models.source import Source
from app.models.category import Category
from app.models.tag import Tag
from app.schemas.news import NewsCreate, NewsUpdate


def get_news_by_id(db: Session, news_id: int) -> Optional[News]:
    return db.query(News).filter(News.id == news_id).first()


def get_news_by_original_id(db: Session, source_id: str, original_id: str) -> Optional[News]:
    return db.query(News).filter(
        News.source_id == source_id,
        News.original_id == original_id
    ).first()


def get_news(
    db: Session,
    skip: int = 0,
    limit: int = 20,
    source_id: Optional[str] = None,
    category_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    search_query: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    is_top: Optional[bool] = None,
    cluster_id: Optional[str] = None,
    include_content: bool = False
) -> List[News]:
    query = db.query(News)
    
    if source_id:
        query = query.filter(News.source_id == source_id)
    
    if category_id:
        query = query.filter(News.category_id == category_id)
    
    if tag_id:
        query = query.join(News.tags).filter(Tag.id == tag_id)
    
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(
            or_(
                News.title.ilike(search_term),
                News.content.ilike(search_term) if include_content else False,
                News.summary.ilike(search_term)
            )
        )
    
    if start_date:
        query = query.filter(News.published_at >= start_date)
    
    if end_date:
        query = query.filter(News.published_at <= end_date)
    
    if is_top is not None:
        query = query.filter(News.is_top == is_top)
    
    if cluster_id:
        query = query.filter(News.cluster_id == cluster_id)
    
    # Always order by published_at desc, then created_at desc
    query = query.order_by(desc(News.published_at), desc(News.created_at))
    
    return query.offset(skip).limit(limit).all()


def get_news_with_relations(
    db: Session,
    news_id: int
) -> Optional[Dict[str, Any]]:
    news = db.query(News).options(
        joinedload(News.source),
        joinedload(News.category),
        joinedload(News.tags)
    ).filter(News.id == news_id).first()
    
    if not news:
        return None
    
    return {
        "news": news,
        "source": news.source,
        "category": news.category,
        "tags": news.tags
    }


def get_news_list_items(
    db: Session,
    skip: int = 0,
    limit: int = 20,
    source_id: Optional[str] = None,
    category_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    search_query: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    is_top: Optional[bool] = None
) -> List[Dict[str, Any]]:
    query = db.query(
        News.id,
        News.title,
        News.url,
        News.source_id,
        Source.name.label("source_name"),
        News.published_at,
        News.image_url,
        News.summary,
        News.category_id,
        Category.name.label("category_name"),
        News.is_top,
        News.view_count,
        News.sentiment_score,
        News.extra,
        News.created_at
    ).join(Source, News.source_id == Source.id
    ).outerjoin(Category, News.category_id == Category.id)
    
    if source_id:
        query = query.filter(News.source_id == source_id)
    
    if category_id:
        query = query.filter(News.category_id == category_id)
    
    if tag_id:
        query = query.join(News.tags).filter(Tag.id == tag_id)
    
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(
            or_(
                News.title.ilike(search_term),
                News.summary.ilike(search_term)
            )
        )
    
    if start_date:
        query = query.filter(News.published_at >= start_date)
    
    if end_date:
        query = query.filter(News.published_at <= end_date)
    
    if is_top is not None:
        query = query.filter(News.is_top == is_top)
    
    # Always order by published_at desc, then created_at desc
    query = query.order_by(desc(News.published_at), desc(News.created_at))
    
    return query.offset(skip).limit(limit).all()


def create_news(db: Session, news: NewsCreate) -> News:
    db_news = News(**news.model_dump())
    db.add(db_news)
    db.commit()
    db.refresh(db_news)
    return db_news


def update_news(db: Session, news_id: int, news: NewsUpdate) -> Optional[News]:
    db_news = get_news_by_id(db, news_id)
    if not db_news:
        return None
    
    update_data = news.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        setattr(db_news, key, value)
    
    db.commit()
    db.refresh(db_news)
    return db_news


def delete_news(db: Session, news_id: int) -> bool:
    db_news = get_news_by_id(db, news_id)
    if not db_news:
        return False
    
    db.delete(db_news)
    db.commit()
    return True


def increment_view_count(db: Session, news_id: int) -> Optional[News]:
    db_news = get_news_by_id(db, news_id)
    if not db_news:
        return None
    
    db_news.view_count += 1
    db.commit()
    db.refresh(db_news)
    return db_news


def get_trending_news(
    db: Session,
    limit: int = 10,
    hours: int = 24,
    category_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    query = db.query(
        News.id,
        News.title,
        News.url,
        News.source_id,
        Source.name.label("source_name"),
        News.published_at,
        News.image_url,
        News.summary,
        News.category_id,
        Category.name.label("category_name"),
        News.is_top,
        News.view_count,
        News.sentiment_score,
        News.extra,
        News.created_at
    ).join(Source, News.source_id == Source.id
    ).outerjoin(Category, News.category_id == Category.id
    ).filter(News.published_at >= cutoff_time)
    
    if category_id:
        query = query.filter(News.category_id == category_id)
    
    # Order by view_count and then published_at
    query = query.order_by(desc(News.view_count), desc(News.published_at))
    
    return query.limit(limit).all()


def add_tag_to_news(db: Session, news_id: int, tag_id: int) -> bool:
    db_news = get_news_by_id(db, news_id)
    db_tag = db.query(Tag).filter(Tag.id == tag_id).first()
    
    if not db_news or not db_tag:
        return False
    
    db_news.tags.append(db_tag)
    db.commit()
    return True


def remove_tag_from_news(db: Session, news_id: int, tag_id: int) -> bool:
    db_news = get_news_by_id(db, news_id)
    db_tag = db.query(Tag).filter(Tag.id == tag_id).first()
    
    if not db_news or not db_tag:
        return False
    
    db_news.tags.remove(db_tag)
    db.commit()
    return True


def update_news_cluster(db: Session, news_id: int, cluster_id: str) -> Optional[News]:
    db_news = get_news_by_id(db, news_id)
    if not db_news:
        return None
    
    db_news.cluster_id = cluster_id
    db.commit()
    db.refresh(db_news)
    return db_news


def get_news_by_cluster(db: Session, cluster_id: str, limit: int = 20) -> List[News]:
    return db.query(News).filter(
        News.cluster_id == cluster_id
    ).order_by(desc(News.published_at)).limit(limit).all() 