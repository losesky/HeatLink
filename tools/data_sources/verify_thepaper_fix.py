#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Verification script to test the thepaper source.
This script tests that the 'thepaper' source is correctly fetching data using Selenium.
"""

import sys
import os

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../.."))
sys.path.insert(0, project_root)

import asyncio
import logging
from sqlalchemy import text
from app.db.session import SessionLocal
from worker.sources.factory import NewsSourceFactory

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """
    Main function to verify thepaper source is working.
    """
    logger.info("Starting thepaper source verification")
    db = SessionLocal()
    
    try:
        # 1. Verify source configuration in database
        source_info = db.execute(
            text("SELECT id, name, type, status FROM sources WHERE id = 'thepaper'")
        ).fetchone()
        
        if not source_info:
            logger.error("No source found with ID 'thepaper'")
            return
        
        logger.info(f"Source info: ID: {source_info[0]}, Name: {source_info[1]}, Type: {source_info[2]}, Status: {source_info[3]}")
        
        # 2. Create source instance using factory
        source = NewsSourceFactory.create_source("thepaper")
        if not source:
            logger.error("Failed to create thepaper source instance")
            return
        
        logger.info(f"Created source: {source.source_id} (Class: {source.__class__.__name__})")
        
        # 3. Test fetching data
        logger.info("Fetching news from thepaper source...")
        news_items = await source.fetch()
        
        if not news_items:
            logger.warning("No news items fetched")
        else:
            logger.info(f"Successfully fetched {len(news_items)} news items")
            
            # Display a few items
            for i, item in enumerate(news_items[:5]):
                logger.info(f"Item {i+1}: {item.title} ({item.url})")
        
        logger.info("Source verification completed successfully")
        
    except Exception as e:
        logger.error(f"Error during verification: {str(e)}", exc_info=True)
    finally:
        # Make sure to close any resources
        if 'source' in locals():
            await source.close()
        db.close()

if __name__ == "__main__":
    asyncio.run(main()) 