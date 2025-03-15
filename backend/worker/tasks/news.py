import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from app.crud.news import get_news_by_original_id, create_news, update_news
from app.crud.source import get_source
from app.db.session import SessionLocal
from app.models.news import News
from app.schemas.news import NewsCreate, NewsUpdate
from worker.celery_app import celery_app
from worker.sources.registry import source_registry
from worker.sources.base import NewsItemModel


logger = logging.getLogger(__name__)


@celery_app.task(name="fetch_all_news")
def fetch_all_news() -> Dict[str, Any]:
    """
    Fetch news from all sources
    """
    logger.info("Starting fetch_all_news task")
    
    # Create event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Load sources from database
        loop.run_until_complete(source_registry.load_sources_from_db())
        
        # Fetch news from all sources
        loop.run_until_complete(source_registry.fetch_all_sources())
        
        # Process news items
        for source_id, source in source_registry.sources.items():
            try:
                # Fetch news items
                news_items = loop.run_until_complete(source.process())
                
                # Save news items to database
                _save_news_items(source_id, news_items)
                
                logger.info(f"Processed {len(news_items)} news items from source {source_id}")
            except Exception as e:
                logger.error(f"Error processing source {source_id}: {str(e)}")
        
        return {"status": "success", "message": "News fetched successfully"}
    except Exception as e:
        logger.error(f"Error in fetch_all_news task: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        loop.close()


@celery_app.task(name="fetch_source_news")
def fetch_source_news(source_id: str) -> Dict[str, Any]:
    """
    Fetch news from a specific source
    """
    logger.info(f"Starting fetch_source_news task for source {source_id}")
    
    # Create event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Load sources from database
        loop.run_until_complete(source_registry.load_sources_from_db())
        
        # Get source
        source = source_registry.get_source(source_id)
        if not source:
            return {"status": "error", "message": f"Source {source_id} not found"}
        
        # Fetch news items
        news_items = loop.run_until_complete(source.process())
        
        # Save news items to database
        _save_news_items(source_id, news_items)
        
        logger.info(f"Processed {len(news_items)} news items from source {source_id}")
        
        return {"status": "success", "message": f"News fetched successfully for source {source_id}"}
    except Exception as e:
        logger.error(f"Error in fetch_source_news task for source {source_id}: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        loop.close()


def _save_news_items(source_id: str, news_items: List[NewsItemModel]) -> None:
    """
    Save news items to database
    """
    db = SessionLocal()
    try:
        # Get source from database
        db_source = get_source(db, source_id=source_id)
        if not db_source:
            logger.warning(f"Source {source_id} not found in database")
            return
        
        # Process each news item
        for item in news_items:
            try:
                # Check if news item already exists
                existing_news = get_news_by_original_id(
                    db, source_id=source_id, original_id=item.id
                )
                
                if existing_news:
                    # Update existing news item if needed
                    _update_existing_news(db, existing_news, item)
                else:
                    # Create new news item
                    _create_new_news(db, source_id, item)
            except Exception as e:
                logger.error(f"Error saving news item {item.id}: {str(e)}")
    finally:
        db.close()


def _create_new_news(db: Session, source_id: str, item: NewsItemModel) -> None:
    """
    Create a new news item in the database
    """
    # Create news item
    news_in = NewsCreate(
        title=item.title,
        url=item.url,
        mobile_url=item.mobile_url,
        content=item.content,
        summary=item.summary,
        image_url=item.image_url,
        published_at=item.published_at or datetime.utcnow(),
        source_id=source_id,
        original_id=item.id,
        author=item.extra.get("author"),
        is_active=True,
        extra=item.extra
    )
    
    # Save to database
    create_news(db, news=news_in)


def _update_existing_news(db: Session, existing_news: News, item: NewsItemModel) -> None:
    """
    Update an existing news item in the database if needed
    """
    # Check if update is needed
    update_needed = False
    update_data = {}
    
    # Check fields that might need updating
    if existing_news.title != item.title:
        update_data["title"] = item.title
        update_needed = True
    
    if existing_news.url != item.url:
        update_data["url"] = item.url
        update_needed = True
    
    if item.mobile_url and existing_news.mobile_url != item.mobile_url:
        update_data["mobile_url"] = item.mobile_url
        update_needed = True
    
    if item.content and existing_news.content != item.content:
        update_data["content"] = item.content
        update_needed = True
    
    if item.summary and existing_news.summary != item.summary:
        update_data["summary"] = item.summary
        update_needed = True
    
    if item.image_url and existing_news.image_url != item.image_url:
        update_data["image_url"] = item.image_url
        update_needed = True
    
    if item.published_at and existing_news.published_at != item.published_at:
        update_data["published_at"] = item.published_at
        update_needed = True
    
    # Update if needed
    if update_needed:
        news_update = NewsUpdate(**update_data)
        update_news(db, news_id=existing_news.id, news=news_update)


@celery_app.task(name="cleanup_old_news")
def cleanup_old_news(days: int = 30) -> Dict[str, Any]:
    """
    Clean up old news items
    """
    logger.info(f"Starting cleanup_old_news task for news older than {days} days")
    
    db = SessionLocal()
    try:
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Get old news items
        old_news = db.query(News).filter(News.published_at < cutoff_date).all()
        
        # Deactivate old news items
        for news in old_news:
            news.is_active = False
        
        # Commit changes
        db.commit()
        
        logger.info(f"Deactivated {len(old_news)} old news items")
        
        return {"status": "success", "message": f"Deactivated {len(old_news)} old news items"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error in cleanup_old_news task: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close() 