#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Fix for thepaper sources duplication.
This script updates the 'thepaper' source to properly use Selenium and migrates
any news data from 'thepaper_selenium' to 'thepaper'.
"""

import sys
sys.path.append('/home/losesky/HeatLink/backend')

import logging
from sqlalchemy import text
from app.db.session import SessionLocal

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """
    Main function to fix the duplicated thepaper source.
    """
    logger.info("Starting thepaper source duplication fix")
    db = SessionLocal()
    
    try:
        # 1. Check if both sources exist
        sources = db.execute(
            text("SELECT id, name, type, status FROM sources WHERE id IN ('thepaper', 'thepaper_selenium')")
        ).fetchall()
        
        if not sources:
            logger.info("No sources found with IDs 'thepaper' or 'thepaper_selenium'")
            return
        
        source_map = {source[0]: source for source in sources}
        logger.info(f"Found sources: {[s[0] for s in sources]}")
        
        # 2. Check how many news items exist for each source
        news_counts = db.execute(
            text("SELECT source_id, COUNT(*) FROM news WHERE source_id IN ('thepaper', 'thepaper_selenium') GROUP BY source_id")
        ).fetchall()
        
        news_count_map = {count[0]: count[1] for count in news_counts}
        logger.info(f"News counts: {news_count_map}")
        
        # 3. Update 'thepaper' type to WEB if needed
        if 'thepaper' in source_map and source_map['thepaper'][2] != 'WEB':
            logger.info(f"Updating 'thepaper' type from '{source_map['thepaper'][2]}' to 'WEB'")
            db.execute(
                text("UPDATE sources SET type = 'WEB', config = NULL WHERE id = 'thepaper'")
            )
        
        # 4. Migrate any news from 'thepaper_selenium' to 'thepaper'
        if 'thepaper_selenium' in news_count_map and news_count_map.get('thepaper_selenium', 0) > 0:
            selenium_news_count = news_count_map.get('thepaper_selenium', 0)
            logger.info(f"Moving {selenium_news_count} news items from 'thepaper_selenium' to 'thepaper'")
            
            # First, check if there are any ID conflicts
            conflicts = db.execute(
                text("""
                SELECT n1.id FROM news n1 
                JOIN news n2 ON n1.id = n2.id 
                WHERE n1.source_id = 'thepaper' AND n2.source_id = 'thepaper_selenium'
                """)
            ).fetchall()
            
            if conflicts:
                conflict_count = len(conflicts)
                logger.warning(f"Found {conflict_count} news items with same ID in both sources")
                # Delete the conflicting items from thepaper_selenium
                conflict_ids = [c[0] for c in conflicts]
                db.execute(
                    text(f"DELETE FROM news WHERE source_id = 'thepaper_selenium' AND id IN :ids"),
                    {"ids": tuple(conflict_ids)}
                )
                logger.info(f"Deleted {conflict_count} conflicting news items from 'thepaper_selenium'")
            
            # Update the source_id for remaining thepaper_selenium news
            rows_updated = db.execute(
                text("UPDATE news SET source_id = 'thepaper' WHERE source_id = 'thepaper_selenium'")
            ).rowcount
            logger.info(f"Updated {rows_updated} news items to use 'thepaper' source_id")
        
        # 5. Delete the redundant thepaper_selenium source if it exists
        if 'thepaper_selenium' in source_map:
            logger.info("Deleting redundant 'thepaper_selenium' source")
            db.execute(
                text("DELETE FROM sources WHERE id = 'thepaper_selenium'")
            )
        
        # Commit the changes
        db.commit()
        logger.info("Successfully fixed thepaper source duplication")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error fixing thepaper source duplication: {str(e)}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main() 