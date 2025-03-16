from typing import Any, List, Dict
import asyncio
import logging
from datetime import datetime
import time

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_superuser
from app.schemas.source_test import (
    SourceTestResult, SourceTestRequest, 
    AllSourcesTestResult, AllSourcesTestRequest
)

# Import the functions from test_sources_report.py
from worker.sources.factory import NewsSourceFactory
from worker.sources.base import NewsSource

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("source_tester_api")

router = APIRouter()

# Reuse the close_source function from test_sources_report.py
async def close_source(source):
    """Close the data source and release resources"""
    if source is None:
        return
    
    try:
        # Call close method
        if hasattr(source, 'close'):
            try:
                await source.close()
                return  # If successfully closed, return directly
            except Exception as e:
                logger.warning(f"Error calling close() method: {str(e)}")
        
        # Try to close http_client
        if hasattr(source, '_http_client') and source._http_client is not None:
            # Access _http_client attribute directly
            if hasattr(source._http_client, 'close'):
                await source._http_client.close()
        
        # Try to close aiohttp sessions
        import aiohttp
        import inspect
        for attr_name in dir(source):
            if attr_name.startswith('_'):
                continue
                
            try:
                # Skip property accessors and coroutines
                attr = getattr(source.__class__, attr_name, None)
                if attr and (inspect.iscoroutine(attr) or inspect.isawaitable(attr) or 
                           inspect.iscoroutinefunction(attr) or isinstance(attr, property)):
                    continue
                
                # Get instance attribute
                attr = getattr(source, attr_name)
                
                # Close aiohttp session
                if isinstance(attr, aiohttp.ClientSession) and not attr.closed:
                    await attr.close()
            except (AttributeError, TypeError):
                # Skip coroutine properties or other attributes that cannot be accessed directly
                pass
    except Exception as e:
        logger.warning(f"Error closing source: {str(e)}")

# Reuse the test_source function from test_sources_report.py
async def test_source(source_type: str, timeout: int = 60) -> dict:
    """Test a single data source"""
    result = {
        "source_type": source_type,
        "success": False,
        "error": None,
        "items_count": 0,
        "elapsed_time": 0
    }
    
    logger.info(f"Testing source: {source_type}")
    
    # Create data source
    source = None
    try:
        source = NewsSourceFactory.create_source(source_type)
        
        # Get data
        start_time = time.time()
        try:
            # Use asyncio.wait_for to add timeout mechanism
            fetch_task = asyncio.create_task(source.fetch())
            news_items = await asyncio.wait_for(fetch_task, timeout=timeout)
            elapsed_time = time.time() - start_time
            
            # Record results
            result["success"] = True
            result["items_count"] = len(news_items)
            result["elapsed_time"] = elapsed_time
            
            logger.info(f"Fetch successful: {len(news_items)} items in {elapsed_time:.2f}s")
        except asyncio.TimeoutError:
            elapsed_time = time.time() - start_time
            error_msg = f"Timeout after {elapsed_time:.2f}s"
            result["error"] = error_msg
            logger.error(error_msg)
        except Exception as e:
            elapsed_time = time.time() - start_time
            error_msg = f"Error fetching data: {str(e)}"
            result["error"] = error_msg
            logger.error(error_msg)
    except Exception as e:
        error_msg = f"Error creating source: {str(e)}"
        result["error"] = error_msg
        logger.error(error_msg)
    finally:
        # Close data source
        if source:
            await close_source(source)
    
    return result

# Reuse the test_all_sources function from test_sources_report.py
async def test_all_sources(timeout: int = 60, max_concurrent: int = 5) -> dict:
    """Test all data sources"""
    start_time = datetime.now()
    
    # Get all default data sources
    sources = NewsSourceFactory.create_default_sources()
    source_types = [source.source_id for source in sources]
    
    # Close all data sources
    for source in sources:
        await close_source(source)
    
    logger.info(f"Testing {len(source_types)} sources...")
    
    # Create semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def test_with_semaphore(source_type: str) -> dict:
        async with semaphore:
            result = await test_source(source_type, timeout=timeout)
            return result
    
    # Create all test tasks
    tasks = [test_with_semaphore(source_type) for source_type in source_types]
    
    # Execute all tasks
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    successful_sources = []
    failed_sources = []
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Task error for {source_types[i]}: {str(result)}")
            failed_sources.append({
                "source_type": source_types[i],
                "error": str(result)
            })
            continue
        
        if result["success"]:
            successful_sources.append({
                "source_type": result["source_type"],
                "items_count": result["items_count"],
                "elapsed_time": result["elapsed_time"]
            })
        else:
            failed_sources.append({
                "source_type": result["source_type"],
                "error": result["error"]
            })
    
    end_time = datetime.now()
    total_time = (end_time - start_time).total_seconds()
    
    return {
        "summary": {
            "total_sources": len(source_types),
            "successful_sources": len(successful_sources),
            "failed_sources": len(failed_sources),
            "success_rate": f"{len(successful_sources) / len(source_types) * 100:.1f}%",
            "total_time": f"{total_time:.2f}s"
        },
        "successful_sources": sorted(successful_sources, key=lambda x: x["source_type"]),
        "failed_sources": sorted(failed_sources, key=lambda x: x["source_type"])
    }

# API Endpoints
@router.get("/source-types", response_model=List[str])
async def get_source_types() -> Any:
    """
    Get all available source types.
    """
    # Get all default data sources
    sources = NewsSourceFactory.create_default_sources()
    source_types = [source.source_id for source in sources]
    
    # Close all data sources
    for source in sources:
        await close_source(source)
    
    return sorted(source_types)

@router.get("/test-source/{source_type}", response_model=SourceTestResult)
async def get_test_source(
    source_type: str,
    timeout: int = 60,
) -> Any:
    """
    Test a single news source using GET method.
    """
    result = await test_source(source_type, timeout)
    return result

@router.post("/test-source", response_model=SourceTestResult)
async def api_test_source(
    *,
    request: SourceTestRequest,
) -> Any:
    """
    Test a single news source.
    """
    result = await test_source(request.source_type, request.timeout)
    return result

@router.post("/test-all-sources", response_model=AllSourcesTestResult)
async def api_test_all_sources(
    *,
    request: AllSourcesTestRequest,
    background_tasks: BackgroundTasks,
) -> Any:
    """
    Test all news sources.
    """
    # Close http_client singleton after test completes
    async def cleanup():
        from worker.utils.http_client import http_client
        await http_client.close()
    
    result = await test_all_sources(request.timeout, request.max_concurrent)
    
    # Add cleanup task to background tasks
    background_tasks.add_task(cleanup)
    
    return result

@router.get("/test-all-sources", response_model=AllSourcesTestResult)
async def get_test_all_sources(
    background_tasks: BackgroundTasks,
    timeout: int = 60,
    max_concurrent: int = 5,
) -> Any:
    """
    Test all news sources using GET method.
    """
    # Close http_client singleton after test completes
    async def cleanup():
        from worker.utils.http_client import http_client
        await http_client.close()
    
    result = await test_all_sources(timeout, max_concurrent)
    
    # Add cleanup task to background tasks
    background_tasks.add_task(cleanup)
    
    return result

@router.get("/sample/{source_type}", response_model=List[Dict[str, Any]])
async def get_source_sample(
    source_type: str,
    limit: int = 5,
    timeout: int = 60,
) -> Any:
    """
    Get sample data from a specific news source to check data format.
    Returns a limited number of news items from the source.
    """
    # Create data source
    source = None
    try:
        source = NewsSourceFactory.create_source(source_type)
        
        # Get data
        fetch_task = asyncio.create_task(source.fetch())
        news_items = await asyncio.wait_for(fetch_task, timeout=timeout)
        
        # Limit the number of items
        limited_items = news_items[:limit]
        
        # Convert to dict for JSON serialization
        result = []
        for item in limited_items:
            if hasattr(item, "__dict__"):
                # If it's an object with __dict__, convert to dict
                item_dict = item.__dict__.copy()
                # Remove private attributes
                item_dict = {k: v for k, v in item_dict.items() if not k.startswith("_")}
                result.append(item_dict)
            elif isinstance(item, dict):
                # If it's already a dict, use it directly
                result.append(item)
            else:
                # Otherwise, try to convert to dict
                result.append(dict(item))
        
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching sample data: {str(e)}"
        )
    finally:
        # Close data source
        if source:
            await close_source(source)

@router.get("/compare-formats", response_model=Dict[str, Any])
async def compare_source_formats(
    sources: str = Query(..., description="Comma-separated list of source types to compare"),
    timeout: int = 60,
) -> Any:
    """
    Compare data formats from multiple news sources.
    Returns a comparison of fields and their types for each source.
    """
    source_list = [s.strip() for s in sources.split(",")]
    if not source_list:
        raise HTTPException(
            status_code=400,
            detail="No sources specified"
        )
    
    result = {}
    
    for source_type in source_list:
        try:
            # Get sample data
            sample = await get_source_sample(source_type, limit=1, timeout=timeout)
            
            if not sample:
                result[source_type] = {"error": "No data returned"}
                continue
            
            # Analyze fields and types
            fields = {}
            for key, value in sample[0].items():
                field_type = type(value).__name__
                fields[key] = field_type
            
            result[source_type] = {
                "fields": fields,
                "sample": sample[0]
            }
        except Exception as e:
            result[source_type] = {"error": str(e)}
    
    return result 