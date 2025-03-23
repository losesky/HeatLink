from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import asyncio
import traceback
import time
import json

from worker.sources.factory import NewsSourceFactory
from worker.sources.provider import DefaultNewsSourceProvider
from worker.stats_wrapper import stats_updater
from app.api import deps

router = APIRouter()

@router.get("/source-types", response_model=List[str])
async def get_source_types():
    """
    获取所有可用的源类型
    
    Returns:
        List[str]: 源类型列表
    """
    try:
        # Get all available source types from the factory
        source_types = NewsSourceFactory.get_available_sources()
        return source_types
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"无法获取源类型列表: {str(e)}"
        )

@router.get("/test-source/{source_id}")
async def test_source(
    source_id: str,
    timeout: int = Query(60, ge=1, le=300, description="Timeout in seconds")
):
    """
    测试单个源
    
    Args:
        source_id: 源ID
        timeout: 超时时间(秒)
        
    Returns:
        Dict: 测试结果
    """
    try:
        # Create a source instance
        source = NewsSourceFactory.create_source(source_id)
        if not source:
            raise HTTPException(
                status_code=404,
                detail=f"找不到源 {source_id}"
            )
            
        # Set a timeout for the test
        start_time = time.time()
        
        try:
            # 将源的fetch方法包装为external类型
            original_fetch = source.fetch
            source.fetch = lambda *args, **kwargs: stats_updater.wrap_fetch(source_id, original_fetch, api_type="external", *args, **kwargs)
            
            # Fetch news with a timeout
            news_items = await asyncio.wait_for(source.get_news(force_update=True), timeout=timeout)
            
            # 恢复原始fetch方法
            source.fetch = original_fetch
            
            # If we get here, the test was successful
            end_time = time.time()
            elapsed_time = end_time - start_time
            
            # Create a sample for the first item
            sample = None
            if news_items and len(news_items) > 0:
                sample = news_items[0].to_dict()
            
            # Get field types from the sample
            field_types = {}
            if sample:
                for field, value in sample.items():
                    field_types[field] = type(value).__name__
            
            return {
                "success": True,
                "elapsed_time": elapsed_time,
                "items_count": len(news_items),
                "sample": sample,
                "fields": field_types
            }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"请求超时 (>{timeout}秒)"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
        finally:
            # Make sure to close the source
            if source:
                await source.close()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"测试源时出错: {str(e)}"
        )

@router.get("/test-all-sources")
async def test_all_sources(
    timeout: int = Query(60, ge=1, le=300, description="Timeout in seconds"),
    max_concurrent: int = Query(5, ge=1, le=20, description="Maximum concurrent tests")
):
    """
    测试所有源
    
    Args:
        timeout: 每个源的超时时间(秒)
        max_concurrent: 最大并发测试数
        
    Returns:
        Dict: 测试结果
    """
    try:
        # Get all available source types
        source_types = NewsSourceFactory.get_available_sources()
        
        # Create a semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def test_source_with_semaphore(source_type):
            """使用信号量限制并发测试数量，并确保调用被修改的test_source函数以正确统计外部API调用"""
            async with semaphore:
                return {
                    "source_type": source_type,
                    "result": await test_source(source_type, timeout)
                }
        
        # Test all sources concurrently
        tasks = [test_source_with_semaphore(source_type) for source_type in source_types]
        results = await asyncio.gather(*tasks)
        
        # Separate successful and failed sources
        successful_sources = []
        failed_sources = []
        
        for result in results:
            source_type = result["source_type"]
            test_result = result["result"]
            
            if test_result.get("success", False):
                successful_sources.append({
                    "source_type": source_type,
                    "elapsed_time": test_result.get("elapsed_time", 0),
                    "items_count": test_result.get("items_count", 0)
                })
            else:
                failed_sources.append({
                    "source_type": source_type,
                    "error": test_result.get("error", "Unknown error")
                })
        
        # Calculate summary statistics
        avg_time = 0
        if successful_sources:
            avg_time = sum(s["elapsed_time"] for s in successful_sources) / len(successful_sources)
        
        total_items = sum(s["items_count"] for s in successful_sources)
        
        summary = {
            "total_sources": len(source_types),
            "successful_sources": len(successful_sources),
            "failed_sources": len(failed_sources),
            "average_time": avg_time,
            "total_items": total_items
        }
        
        return {
            "summary": summary,
            "successful_sources": successful_sources,
            "failed_sources": failed_sources
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"测试所有源时出错: {str(e)}"
        )

@router.get("/compare-formats")
async def compare_formats(
    sources: str = Query(..., description="Comma-separated list of source types to compare"),
    timeout: int = Query(60, ge=1, le=300, description="Timeout in seconds")
):
    """
    比较多个源的数据格式
    
    Args:
        sources: 要比较的源ID列表，逗号分隔
        timeout: 超时时间(秒)
        
    Returns:
        Dict: 比较结果
    """
    try:
        # Parse sources list
        source_list = [s.strip() for s in sources.split(",") if s.strip()]
        
        if not source_list:
            raise HTTPException(
                status_code=400,
                detail="请至少指定一个源"
            )
        
        # Create a semaphore to limit concurrency
        semaphore = asyncio.Semaphore(5)  # Limit to 5 concurrent tests
        
        async def test_source_with_semaphore(source_type):
            """使用信号量限制并发测试数量，并确保调用被修改的test_source函数以正确统计外部API调用"""
            async with semaphore:
                return {
                    "source_type": source_type,
                    "result": await test_source(source_type, timeout)
                }
        
        # Test all specified sources concurrently
        tasks = [test_source_with_semaphore(source_type) for source_type in source_list]
        results = await asyncio.gather(*tasks)
        
        # Format the results
        comparison_result = {}
        
        for result in results:
            source_type = result["source_type"]
            test_result = result["result"]
            
            if test_result.get("success", False):
                comparison_result[source_type] = {
                    "sample": test_result.get("sample", {}),
                    "fields": test_result.get("fields", {})
                }
            else:
                comparison_result[source_type] = {
                    "error": test_result.get("error", "Unknown error")
                }
        
        return comparison_result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"比较源格式时出错: {str(e)}"
        ) 