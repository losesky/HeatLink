import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.source import Source, SourceAlias, SourceType
from app.schemas.source import SourceCreate, SourceUpdate


def get_source(db: Session, source_id: str) -> Optional[Source]:
    return db.query(Source).filter(Source.id == source_id).first()


def get_source_by_alias(db: Session, alias: str) -> Optional[Source]:
    source_alias = db.query(SourceAlias).filter(SourceAlias.alias == alias).first()
    if source_alias:
        return source_alias.source
    return None


def get_sources(
    db: Session, 
    skip: int = 0, 
    limit: int = 100, 
    active_only: bool = None,
    type_filter: Optional[SourceType] = None,
    category_id: Optional[int] = None,
    country: Optional[str] = None,
    language: Optional[str] = None
) -> List[Source]:
    query = db.query(Source)
    
    if active_only is not None:
        query = query.filter(Source.active == active_only)
    
    if type_filter:
        query = query.filter(Source.type == type_filter)
    
    if category_id:
        query = query.filter(Source.category_id == category_id)
    
    if country:
        query = query.filter(Source.country == country)
    
    if language:
        query = query.filter(Source.language == language)
    
    return query.order_by(Source.priority.desc()).offset(skip).limit(limit).all()


def get_active_sources(db: Session) -> List[Source]:
    return db.query(Source).filter(Source.active == True).order_by(Source.priority.desc()).all()


def create_source(db: Session, source: SourceCreate) -> Source:
    db_source = Source(
        id=source.id,
        name=source.name,
        description=source.description,
        url=source.url,
        type=source.type,
        active=source.active,
        update_interval=datetime.timedelta(seconds=source.update_interval),
        cache_ttl=datetime.timedelta(seconds=source.cache_ttl),
        category_id=source.category_id,
        country=source.country,
        language=source.language,
        config=source.config,
        priority=source.priority
    )
    db.add(db_source)
    db.commit()
    db.refresh(db_source)
    return db_source


def update_source(db: Session, db_obj: Source, obj_in: SourceUpdate) -> Optional[Source]:
    """
    Update a source in the database using the provided data
    """
    if not db_obj:
        return None
    
    update_data = obj_in.model_dump(exclude_unset=True)
    
    # Convert interval fields from seconds to timedelta
    if "update_interval" in update_data:
        update_data["update_interval"] = datetime.timedelta(seconds=update_data["update_interval"])
    
    if "cache_ttl" in update_data:
        update_data["cache_ttl"] = datetime.timedelta(seconds=update_data["cache_ttl"])
    
    for key, value in update_data.items():
        setattr(db_obj, key, value)
    
    db.commit()
    db.refresh(db_obj)
    return db_obj


def delete_source(db: Session, source_id: str) -> bool:
    db_source = get_source(db, source_id)
    if not db_source:
        return False
    
    db.delete(db_source)
    db.commit()
    return True


def update_source_last_updated(db: Session, source_id: str) -> Optional[Source]:
    db_source = get_source(db, source_id)
    if not db_source:
        return None
    
    db_source.last_updated = datetime.datetime.utcnow()
    db_source.error_count = 0
    db_source.last_error = None
    
    db.commit()
    db.refresh(db_source)
    return db_source


def increment_source_error_count(db: Session, source_id: str, error_message: str) -> Optional[Source]:
    db_source = get_source(db, source_id)
    if not db_source:
        return None
    
    db_source.error_count += 1
    db_source.last_error = error_message
    
    db.commit()
    db.refresh(db_source)
    return db_source


def get_source_with_stats(db: Session, id: str) -> Optional[Source]:
    from app.models.news import News
    
    result = db.query(
        Source,
        func.count(News.id).label("news_count"),
        func.max(News.published_at).label("latest_news_time")
    ).outerjoin(News).filter(Source.id == id).group_by(Source.id).first()
    
    if not result:
        return None
    
    source, news_count, latest_news_time = result
    
    # Add stats to the source object as attributes
    source.news_count = news_count
    source.latest_news_time = latest_news_time
    
    return source


def create_source_alias(db: Session, alias: str, source_id: str) -> Optional[SourceAlias]:
    db_source = get_source(db, source_id)
    if not db_source:
        return None
    
    db_alias = SourceAlias(
        alias=alias,
        source_id=source_id
    )
    
    db.add(db_alias)
    db.commit()
    db.refresh(db_alias)
    return db_alias


def delete_source_alias(db: Session, alias: str) -> bool:
    db_alias = db.query(SourceAlias).filter(SourceAlias.alias == alias).first()
    if not db_alias:
        return False
    
    db.delete(db_alias)
    db.commit()
    return True 