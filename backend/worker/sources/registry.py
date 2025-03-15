import asyncio
import logging
from typing import Dict, List, Optional, Type, Any

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.source import Source as SourceModel
from worker.sources.base import NewsSource, NewsItemModel
from worker.sources.rss import RSSNewsSource
from worker.sources.rest_api import RESTNewsSource


logger = logging.getLogger(__name__)


class SourceRegistry:
    """
    Registry for news sources
    """
    
    def __init__(self):
        self.sources: Dict[str, NewsSource] = {}
        self.source_types: Dict[str, Type[NewsSource]] = {
            "rss": RSSNewsSource,
            "rest_api": RESTNewsSource,
        }
    
    def register_source_type(self, source_type: str, source_class: Type[NewsSource]) -> None:
        """
        Register a new source type
        """
        self.source_types[source_type] = source_class
    
    def get_source(self, source_id: str) -> Optional[NewsSource]:
        """
        Get a source by ID
        """
        return self.sources.get(source_id)
    
    def get_all_sources(self) -> List[NewsSource]:
        """
        Get all sources
        """
        return list(self.sources.values())
    
    async def load_sources_from_db(self) -> None:
        """
        Load sources from database
        """
        db = SessionLocal()
        try:
            # Get all active sources from database
            db_sources = db.query(SourceModel).filter(SourceModel.is_active == True).all()
            
            # Create source instances
            for db_source in db_sources:
                try:
                    # Get source type class
                    source_type = db_source.type
                    if source_type not in self.source_types:
                        logger.warning(f"Unknown source type: {source_type} for source {db_source.id}")
                        continue
                    
                    source_class = self.source_types[source_type]
                    
                    # Create source instance with parameters from database
                    source_params = db_source.parameters or {}
                    
                    # Add common parameters
                    common_params = {
                        "source_id": db_source.id,
                        "name": db_source.name,
                        "update_interval": db_source.update_interval,
                        "category": db_source.category,
                        "country": db_source.country,
                        "language": db_source.language,
                    }
                    
                    # Merge parameters
                    source_params.update(common_params)
                    
                    # Create source instance
                    source = source_class(**source_params)
                    
                    # Add to registry
                    self.sources[db_source.id] = source
                    logger.info(f"Loaded source: {db_source.id} ({db_source.name})")
                except Exception as e:
                    logger.error(f"Error loading source {db_source.id}: {str(e)}")
        finally:
            db.close()
    
    async def fetch_all_sources(self) -> Dict[str, List[NewsItemModel]]:
        """
        Fetch news from all sources
        """
        results: Dict[str, List[NewsItemModel]] = {}
        tasks = []
        
        # Create tasks for each source
        for source_id, source in self.sources.items():
            task = asyncio.create_task(self._fetch_source(source_id, source))
            tasks.append(task)
        
        # Wait for all tasks to complete
        await asyncio.gather(*tasks)
        
        return results
    
    async def _fetch_source(self, source_id: str, source: NewsSource) -> None:
        """
        Fetch news from a single source
        """
        try:
            # Process source
            news_items = await source.process()
            logger.info(f"Fetched {len(news_items)} news items from {source_id}")
            
            # TODO: Save news items to database
            
        except Exception as e:
            logger.error(f"Error fetching news from {source_id}: {str(e)}")


# Create singleton instance
source_registry = SourceRegistry() 