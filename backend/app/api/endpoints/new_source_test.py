from typing import List, Dict, Any, Optional
import asyncio
import time
import logging
from fastapi import APIRouter, HTTPException, Query

from worker.sources.factory import NewsSourceFactory

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/source-types")
async def get_source_types():
    """获取所有可用的新闻源类型"""
    try:
        source_types = NewsSourceFactory.get_available_sources()
        return source_types  # 直接返回数组，不包装在对象中
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取新闻源类型失败: {str(e)}")

@router.get("/test-source/{source_type}")
async def test_source(source_type: str, timeout: int = 60):
    """
    测试单个新闻源
    
    :param source_type: 新闻源类型
    :param timeout: 超时时间（秒）
    :return: 测试结果
    """
    source = None
    try:
        start_time = time.time()
        source = NewsSourceFactory.create_source(source_type)
        
        if not source:
            raise HTTPException(status_code=404, detail=f"找不到新闻源类型: {source_type}")
        
        # 设置超时
        try:
            items = await asyncio.wait_for(source.get_news(force_update=True), timeout=timeout)
            elapsed_time = time.time() - start_time
            
            # 返回页面期望的格式
            return {
                "success": True,
                "source_type": source_type,
                "items_count": len(items) if items else 0,
                "elapsed_time": elapsed_time
            }
        except asyncio.TimeoutError:
            elapsed_time = time.time() - start_time
            return {
                "success": False,
                "source_type": source_type,
                "items_count": 0,
                "elapsed_time": elapsed_time,
                "error": f"获取超时，超过 {timeout} 秒"
            }
    except Exception as e:
        elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
        return {
            "success": False,
            "source_type": source_type,
            "items_count": 0,
            "elapsed_time": elapsed_time,
            "error": str(e)
        }
    finally:
        # 确保源被正确关闭，无论请求成功或失败
        if source and hasattr(source, 'close') and callable(source.close):
            try:
                await source.close()
            except Exception as e:
                # 仅记录错误，不影响返回结果
                logger.error(f"关闭源 {source_type} 时出错: {str(e)}")

@router.get("/test-all-sources")
async def test_all_sources(
    timeout: int = 60,
    max_concurrent: int = 5,
    source_types: Optional[List[str]] = Query(None)
):
    """
    测试所有新闻源或指定的新闻源
    
    :param timeout: 每个源的超时时间（秒）
    :param max_concurrent: 最大并发测试数量
    :param source_types: 指定要测试的源类型列表，为空则测试所有
    :return: 测试结果
    """
    try:
        all_source_types = source_types or NewsSourceFactory.get_available_sources()
        
        # 创建信号量以限制并发数
        semaphore = asyncio.Semaphore(max_concurrent)
        
        # 测试所有源的协程任务
        async def test_source_with_semaphore(source_type):
            async with semaphore:
                source = None
                try:
                    start_time = time.time()
                    source = NewsSourceFactory.create_source(source_type)
                    
                    if not source:
                        return {
                            "success": False,
                            "source_type": source_type,
                            "items_count": 0,
                            "elapsed_time": 0,
                            "error": f"找不到新闻源类型: {source_type}"
                        }
                    
                    # 设置超时
                    try:
                        items = await asyncio.wait_for(source.get_news(force_update=True), timeout=timeout)
                        elapsed_time = time.time() - start_time
                        
                        return {
                            "success": True,
                            "source_type": source_type,
                            "items_count": len(items) if items else 0,
                            "elapsed_time": elapsed_time
                        }
                    except asyncio.TimeoutError:
                        elapsed_time = time.time() - start_time
                        return {
                            "success": False,
                            "source_type": source_type,
                            "items_count": 0,
                            "elapsed_time": elapsed_time,
                            "error": f"获取超时，超过 {timeout} 秒"
                        }
                except Exception as e:
                    elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
                    return {
                        "success": False,
                        "source_type": source_type,
                        "items_count": 0,
                        "elapsed_time": elapsed_time,
                        "error": str(e)
                    }
                finally:
                    # 确保源被正确关闭，无论请求成功或失败
                    if source and hasattr(source, 'close') and callable(source.close):
                        try:
                            await source.close()
                        except Exception as e:
                            # 仅记录错误，不影响返回结果
                            logger.error(f"关闭源 {source_type} 时出错: {str(e)}")
        
        # 创建所有任务
        tasks = [test_source_with_semaphore(st) for st in all_source_types]
        
        # 开始计时
        total_start_time = time.time()
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks)
        
        # 计算总耗时
        total_elapsed_time = time.time() - total_start_time
        
        # 分离成功和失败的结果
        successful_results = [r for r in results if r["success"]]
        failed_results = [r for r in results if not r["success"]]
        
        # 直接返回页面期望的格式
        return {
            "summary": {
                "total_sources": len(results),
                "successful_sources": len(successful_results),
                "failed_sources": len(failed_results),
                "success_rate": len(successful_results) / len(results) if results else 0,
                "total_time": total_elapsed_time
            },
            "successful_sources": successful_results,
            "failed_sources": failed_results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"测试所有新闻源失败: {str(e)}") 