import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from celery import Task

from app.crud.news import get_news_by_original_id, create_news, update_news
from app.crud.source import get_source
from app.db.session import SessionLocal
from app.models.news import News
from app.schemas.news import NewsCreate, NewsUpdate
from worker.celery_app import celery_app
from worker.sources.registry import source_registry
from worker.sources.base import NewsItemModel
from celery.utils.log import get_task_logger
from app.core.config import settings
from worker.sources.manager import source_manager


logger = get_task_logger(__name__)


@celery_app.task(bind=True, name="news.fetch_high_frequency_sources")
def fetch_high_frequency_sources(self: Task) -> Dict[str, Any]:
    """
    获取高频更新的新闻源（每10分钟）
    主要是社交媒体等实时性较强的源
    """
    logger.info("Starting high frequency news fetch task")
    
    try:
        # 获取所有高频更新的新闻源（更新间隔小于等于15分钟）
        sources = [
            source for source in source_manager.get_all_sources()
            if source.update_interval <= 900  # 15分钟 = 900秒
        ]
        
        if not sources:
            logger.info("No high frequency sources found")
            return {"status": "success", "message": "No high frequency sources found"}
        
        # 获取所有高频源的新闻
        results = asyncio.run(_fetch_sources_news(sources))
        
        return {
            "status": "success",
            "message": f"Fetched news from {len(results)} high frequency sources",
            "sources": [source.source_id for source in sources],
            "total_news": sum(len(news) for news in results.values())
        }
    except Exception as e:
        logger.error(f"Error in high frequency news fetch task: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True, name="news.fetch_medium_frequency_sources")
def fetch_medium_frequency_sources(self: Task) -> Dict[str, Any]:
    """
    获取中频更新的新闻源（每30分钟）
    主要是新闻网站等更新较频繁的源
    """
    logger.info("Starting medium frequency news fetch task")
    
    try:
        # 获取所有中频更新的新闻源（更新间隔大于15分钟且小于等于45分钟）
        sources = [
            source for source in source_manager.get_all_sources()
            if 900 < source.update_interval <= 2700  # 15-45分钟
        ]
        
        if not sources:
            logger.info("No medium frequency sources found")
            return {"status": "success", "message": "No medium frequency sources found"}
        
        # 获取所有中频源的新闻
        results = asyncio.run(_fetch_sources_news(sources))
        
        return {
            "status": "success",
            "message": f"Fetched news from {len(results)} medium frequency sources",
            "sources": [source.source_id for source in sources],
            "total_news": sum(len(news) for news in results.values())
        }
    except Exception as e:
        logger.error(f"Error in medium frequency news fetch task: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True, name="news.fetch_low_frequency_sources")
def fetch_low_frequency_sources(self: Task) -> Dict[str, Any]:
    """
    获取低频更新的新闻源（每小时或更长）
    主要是博客、周刊等更新不频繁的源
    """
    logger.info("Starting low frequency news fetch task")
    
    try:
        # 获取所有低频更新的新闻源（更新间隔大于45分钟）
        sources = [
            source for source in source_manager.get_all_sources()
            if source.update_interval > 2700  # 45分钟以上
        ]
        
        if not sources:
            logger.info("No low frequency sources found")
            return {"status": "success", "message": "No low frequency sources found"}
        
        # 获取所有低频源的新闻
        results = asyncio.run(_fetch_sources_news(sources))
        
        return {
            "status": "success",
            "message": f"Fetched news from {len(results)} low frequency sources",
            "sources": [source.source_id for source in sources],
            "total_news": sum(len(news) for news in results.values())
        }
    except Exception as e:
        logger.error(f"Error in low frequency news fetch task: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True, name="news.fetch_all_news")
def fetch_all_news(self: Task) -> Dict[str, Any]:
    """
    获取所有新闻源的新闻
    """
    logger.info("Starting fetch all news task")
    
    try:
        # 获取所有新闻源
        sources = source_manager.get_all_sources()
        
        if not sources:
            logger.info("No sources found")
            return {"status": "success", "message": "No sources found"}
        
        # 获取所有源的新闻
        results = asyncio.run(_fetch_sources_news(sources))
        
        return {
            "status": "success",
            "message": f"Fetched news from {len(results)} sources",
            "sources": [source.source_id for source in sources],
            "total_news": sum(len(news) for news in results.values())
        }
    except Exception as e:
        logger.error(f"Error in fetch all news task: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True, name="news.fetch_source_news")
def fetch_source_news(self: Task, source_id: str) -> Dict[str, Any]:
    """
    获取指定新闻源的新闻
    """
    logger.info(f"Starting fetch news task for source: {source_id}")
    
    try:
        # 获取指定新闻源
        source = source_manager.get_source(source_id)
        
        if not source:
            logger.warning(f"Source not found: {source_id}")
            return {"status": "error", "message": f"Source not found: {source_id}"}
        
        # 获取新闻
        news_items = asyncio.run(_fetch_source_news(source))
        
        # 保存到数据库
        saved_count = _save_news_to_db(news_items)
        
        return {
            "status": "success",
            "message": f"Fetched {len(news_items)} news items from source {source_id}",
            "saved": saved_count
        }
    except Exception as e:
        logger.error(f"Error in fetch source news task for {source_id}: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True, name="news.cleanup_old_news")
def cleanup_old_news(self: Task, days: int = 30) -> Dict[str, Any]:
    """
    清理旧新闻
    默认清理30天前的新闻
    """
    logger.info(f"Starting cleanup old news task (older than {days} days)")
    
    try:
        db = SessionLocal()
        try:
            # 计算截止日期
            cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=days)
            
            # 删除旧新闻
            deleted_count = db.query(News).filter(News.published_at < cutoff_date).delete()
            db.commit()
            
            logger.info(f"Deleted {deleted_count} old news items")
            return {
                "status": "success",
                "message": f"Deleted {deleted_count} news items older than {days} days"
            }
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error in cleanup old news task: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True, name="news.analyze_news_trends")
def analyze_news_trends(self: Task, days: int = 7) -> Dict[str, Any]:
    """
    分析新闻趋势
    默认分析最近7天的新闻
    """
    logger.info(f"Starting analyze news trends task (last {days} days)")
    
    try:
        db = SessionLocal()
        try:
            # 计算起始日期
            start_date = datetime.datetime.utcnow() - datetime.timedelta(days=days)
            
            # 获取最近的新闻
            recent_news = db.query(News).filter(News.published_at >= start_date).all()
            
            if not recent_news:
                logger.info(f"No news found in the last {days} days")
                return {
                    "status": "success",
                    "message": f"No news found in the last {days} days"
                }
            
            # TODO: 实现趋势分析算法
            # 这里可以实现关键词提取、聚类、热度计算等
            
            logger.info(f"Analyzed {len(recent_news)} news items")
            return {
                "status": "success",
                "message": f"Analyzed {len(recent_news)} news items from the last {days} days"
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error in analyze news trends task: {str(e)}")
        return {"status": "error", "message": str(e)}


async def _fetch_sources_news(sources: List[Any]) -> Dict[str, List[Any]]:
    """
    获取多个新闻源的新闻
    """
    results = {}
    
    # 创建任务列表
    tasks = [_fetch_source_news(source) for source in sources]
    
    # 并发执行任务
    completed_tasks = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理结果
    for i, result in enumerate(completed_tasks):
        source = sources[i]
        if isinstance(result, Exception):
            logger.error(f"Error fetching news from source {source.source_id}: {str(result)}")
            results[source.source_id] = []
        else:
            results[source.source_id] = result
            # 保存到数据库
            _save_news_to_db(result)
    
    return results


async def _fetch_source_news(source: Any) -> List[Any]:
    """
    获取单个新闻源的新闻
    """
    try:
        # 获取新闻源的新闻
        news_items = await source.get_news(force_update=True)
        logger.info(f"Fetched {len(news_items)} news items from source {source.source_id}")
        return news_items
    except Exception as e:
        logger.error(f"Error fetching news from source {source.source_id}: {str(e)}")
        raise


def _save_news_to_db(news_items: List[Any]) -> int:
    """
    保存新闻到数据库
    返回保存的新闻数量
    """
    if not news_items:
        return 0
    
    db = SessionLocal()
    try:
        saved_count = 0
        
        for item in news_items:
            try:
                # 检查新闻是否已存在
                existing_news = db.query(News).filter(News.id == item.id).first()
                
                if existing_news:
                    # 更新现有新闻
                    existing_news.title = item.title
                    existing_news.url = item.url
                    existing_news.mobile_url = item.mobile_url
                    existing_news.content = item.content
                    existing_news.summary = item.summary
                    existing_news.image_url = item.image_url
                    existing_news.published_at = item.published_at
                    existing_news.is_top = item.is_top
                    existing_news.extra = item.extra
                    existing_news.updated_at = datetime.datetime.utcnow()
                else:
                    # 创建新新闻
                    news = News(
                        id=item.id,
                        title=item.title,
                        url=item.url,
                        mobile_url=item.mobile_url,
                        content=item.content,
                        summary=item.summary,
                        image_url=item.image_url,
                        published_at=item.published_at,
                        is_top=item.is_top,
                        extra=item.extra,
                        source_id=item.extra.get("source_id"),
                        created_at=datetime.datetime.utcnow(),
                        updated_at=datetime.datetime.utcnow()
                    )
                    db.add(news)
                    saved_count += 1
            except Exception as e:
                logger.error(f"Error saving news item {item.id}: {str(e)}")
                continue
        
        db.commit()
        logger.info(f"Saved {saved_count} news items to database")
        return saved_count
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving news to database: {str(e)}")
        return 0
    finally:
        db.close()


def init_sources():
    """
    初始化新闻源
    """
    # 注册默认新闻源
    source_manager.register_default_sources()
    logger.info("Initialized default news sources")

# 初始化新闻源
init_sources() 