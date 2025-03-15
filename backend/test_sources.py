#!/usr/bin/env python
"""
Test script for news source adapters
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add the parent directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from worker.sources.examples import example_sources, register_example_sources
from worker.sources.registry import source_registry


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def test_source(source_id):
    """
    Test a specific source
    """
    source = source_registry.get_source(source_id)
    if not source:
        logger.error(f"Source {source_id} not found")
        return
    
    logger.info(f"Testing source: {source.name} ({source_id})")
    
    try:
        # Fetch news items
        news_items = await source.process()
        
        logger.info(f"Fetched {len(news_items)} news items from {source_id}")
        
        # Print first item details
        if news_items:
            item = news_items[0]
            logger.info(f"First item: {item.title}")
            logger.info(f"URL: {item.url}")
            logger.info(f"Published: {item.published_at}")
            logger.info(f"Summary: {item.summary[:100]}...")
    except Exception as e:
        logger.error(f"Error testing source {source_id}: {str(e)}")


async def test_all_sources():
    """
    Test all sources
    """
    for source_id in source_registry.sources:
        await test_source(source_id)


async def main():
    """
    Main function
    """
    # Register example sources
    register_example_sources(source_registry)
    
    # Get source ID from command line arguments
    if len(sys.argv) > 1:
        source_id = sys.argv[1]
        await test_source(source_id)
    else:
        # Test all sources
        await test_all_sources()


if __name__ == "__main__":
    asyncio.run(main()) 