from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import asyncio
import traceback
import time
import json
import logging
import datetime

from worker.sources.factory import NewsSourceFactory
from worker.sources.provider import DefaultNewsSourceProvider
from worker.stats_wrapper import stats_updater
from app.api import deps

# Initialize global logger
logger = logging.getLogger(__name__)

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
    # 特殊处理"test"源ID，返回模拟数据
    if source_id == "test":
        # 返回一个成功的响应
        return {
            "success": True,
            "source_name": "测试源示例",
            "elapsed_time": 0.5,
            "items_count": 2,
            "sample": {
                "id": "test-id-1",
                "title": "测试新闻标题",
                "url": "https://example.com/news/1",
                "source_id": "test",
                "source_name": "测试源示例",
                "published_at": datetime.datetime.now().isoformat(),
                "content": "这是一个测试内容示例",
                "summary": "测试摘要"
            },
            "fields": {
                "id": "str",
                "title": "str",
                "url": "str",
                "source_id": "str",
                "source_name": "str",
                "published_at": "str",
                "content": "str",
                "summary": "str"
            }
        }
    
    try:
        # 尝试从数据库获取源配置
        db_config = None
        source_data = {}
        try:
            import psycopg2
            conn = psycopg2.connect('postgresql://postgres:postgres@localhost:5432/heatlink_dev')
            cur = conn.cursor()
            
            # 获取完整的源信息
            cur.execute("SELECT id, name, url, country, language, config, need_proxy, proxy_fallback, proxy_group FROM sources WHERE id = %s", (source_id,))
            row = cur.fetchone()
            conn.close()
            
            if row:
                source_data = {
                    "id": row[0],
                    "name": row[1],
                    "url": row[2],
                    "country": row[3],
                    "language": row[4],
                    "config": row[5],
                    "need_proxy": row[6],
                    "proxy_fallback": row[7],
                    "proxy_group": row[8]
                }
                db_config = row[5]
                logger.info(f"从数据库获取到源 {source_id} 的配置: {db_config}")
                
                # 如果有代理设置，添加到config中
                if source_data["need_proxy"]:
                    if not db_config:
                        db_config = {}
                    db_config["need_proxy"] = source_data["need_proxy"]
                    db_config["proxy_fallback"] = source_data["proxy_fallback"]
                    db_config["proxy_group"] = source_data["proxy_group"]
                    logger.info(f"源 {source_id} 使用代理设置: group={source_data['proxy_group']}, fallback={source_data['proxy_fallback']}")
                
                if source_id.startswith('custom-'):
                    logger.info(f"处理自定义源: {source_id}, URL: {source_data['url']}")
        except Exception as e:
            logger.error(f"从数据库获取源配置失败: {str(e)}")
        
        # Create a source instance with database config if available
        if db_config and source_id.startswith('custom-'):
            # 对于自定义源，传递更完整的信息
            # 记录数据库配置信息
            logger.info(f"自定义源 {source_id} 的数据库配置: use_selenium={db_config.get('use_selenium', False)}")
            
            source = NewsSourceFactory.create_source(
                source_type=source_id, 
                config=db_config,
                name=source_data.get("name", source_id),
                url=source_data.get("url", ""),
                country=source_data.get("country", "global"),
                language=source_data.get("language", "en")
            )
            logger.info(f"使用数据库配置创建自定义源 {source_id}")
        elif db_config:
            source = NewsSourceFactory.create_source(source_id, config=db_config)
            logger.info(f"使用数据库配置创建源 {source_id}")
        else:
            source = NewsSourceFactory.create_source(source_id)
            logger.info(f"使用默认配置创建源 {source_id}")
            
        if not source:
            raise HTTPException(
                status_code=404,
                detail=f"找不到源 {source_id}"
            )
            
        # 特别记录CLS源的配置（调试用）
        if source_id.startswith('cls'):
            logger.info(f"CLS源配置详情:")
            logger.info(f"- use_selenium: {getattr(source, 'use_selenium', None)}")
            logger.info(f"- use_direct_api: {getattr(source, 'use_direct_api', None)}")
            logger.info(f"- use_scraping: {getattr(source, 'use_scraping', None)}")
            logger.info(f"- use_backup_api: {getattr(source, 'use_backup_api', None)}")
            
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

@router.post("/create-custom-source", response_model=dict)
async def create_custom_source(source_data: dict):
    """
    创建自定义源适配器
    
    根据提供的配置信息，创建一个新的源适配器，并将其注册到数据库
    
    Args:
        source_data: 源配置信息，包含ID、名称、URL、CSS选择器等
        
    Returns:
        dict: 创建结果
    """
    try:
        from app.db.session import SessionLocal
        from app.models.source import Source, SourceType, SourceStatus
        from app.models.category import Category
        import datetime
        import json

        # 处理API健康检查的空请求
        if not source_data or source_data == {}:
            return {
                "success": False,
                "message": "API端点可用，但需要提供源配置信息",
                "required_fields": ["id", "name", "url", "selectors"],
                "example": {
                    "id": "custom-example",
                    "name": "示例源",
                    "url": "https://example.com/news",
                    "selectors": {
                        "item": ".news-item",
                        "title": ".news-title",
                        "link": ".news-link",
                        "summary": ".news-summary"
                    }
                }
            }
            
        # 验证必填字段
        required_fields = ["id", "name", "url", "selectors"]
        for field in required_fields:
            if field not in source_data:
                raise HTTPException(
                    status_code=400,
                    detail=f"缺少必填字段: {field}"
                )
                
        # 验证选择器
        selectors = source_data.get("selectors", {})
        required_selectors = ["item", "title"]
        for selector in required_selectors:
            if selector not in selectors or not selectors[selector]:
                raise HTTPException(
                    status_code=400,
                    detail=f"缺少必填选择器: {selector}"
                )
                
        # 确保源ID以custom-开头
        source_id = source_data["id"]
        if not source_id.startswith("custom-"):
            source_id = f"custom-{source_id}"
            source_data["id"] = source_id
            logger.info(f"自动添加'custom-'前缀到源ID: {source_id}")
        
        # 创建数据库会话
        db = SessionLocal()
        try:
            # 检查ID是否已存在
            existing_source = db.query(Source).filter(Source.id == source_id).first()
            if existing_source:
                raise HTTPException(
                    status_code=400,
                    detail=f"ID '{source_id}' 已存在"
                )
                
            # 准备配置
            config = {
                "selectors": selectors,
                "use_selenium": bool(source_data.get("use_selenium", False)),
                "auto_generated": True,
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": source_data.get("language", "en") + ",en-US;q=0.8,en;q=0.5",
                    "Connection": "keep-alive"
                }
            }
            
            # 添加代理设置到配置
            if source_data.get("need_proxy", False):
                config["need_proxy"] = True
                config["proxy_fallback"] = bool(source_data.get("proxy_fallback", True))
                config["proxy_group"] = source_data.get("proxy_group", "default")
            
            # 输出调试信息
            logger.info(f"创建自定义源，配置信息: selectors={selectors}, use_selenium={config['use_selenium']}, need_proxy={config.get('need_proxy', False)}")
            
            # 查找分类ID
            category_id = None
            category_slug = source_data.get("category")
            if category_slug:
                category = db.query(Category).filter(Category.slug == category_slug).first()
                if category:
                    category_id = category.id
                    logger.info(f"找到分类 '{category_slug}' 的ID: {category_id}")
                else:
                    logger.warning(f"找不到分类 '{category_slug}'，将使用默认分类")
            
            # 创建源
            new_source = Source(
                id=source_id,
                name=source_data["name"],
                description=f"Auto-generated source for {source_data['url']}",
                url=source_data["url"],
                type=SourceType.WEB,
                status=SourceStatus.INACTIVE,
                update_interval=datetime.timedelta(seconds=source_data.get("update_interval", 1800)),
                cache_ttl=datetime.timedelta(seconds=source_data.get("cache_ttl", 900)),
                category_id=category_id,
                country=source_data.get("country", "US"),
                language=source_data.get("language", "en"),
                config=config,
                # 添加代理相关设置
                need_proxy=bool(source_data.get("need_proxy", False)),
                proxy_fallback=bool(source_data.get("proxy_fallback", True)),
                proxy_group=source_data.get("proxy_group", "default") if source_data.get("need_proxy") else None,
                created_at=datetime.datetime.utcnow(),
                updated_at=datetime.datetime.utcnow()
            )
            
            db.add(new_source)
            db.commit()
            db.refresh(new_source)
            
            # 返回结果
            return {
                "success": True,
                "message": f"源 '{new_source.name}' 创建成功",
                "source": {
                    "id": new_source.id,
                    "name": new_source.name,
                    "url": new_source.url,
                    "status": new_source.status
                }
            }
            
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"创建自定义源时出错: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"创建源失败: {str(e)}"
        )

@router.post("/test-custom-source", response_model=dict)
async def test_custom_source(source_data: dict):
    """
    测试自定义源适配器
    
    根据提供的配置信息，创建一个临时源适配器并进行测试
    
    Args:
        source_data: 源配置信息，包含ID、名称、URL、CSS选择器等
        
    Returns:
        dict: 测试结果
    """
    source = None
    try:
        import random
        import time
        
        # 设置一个记录器来捕获调试信息
        debug_logs = []
        debug_handler = logging.StreamHandler()
        debug_handler.setLevel(logging.INFO)
        
        class DebugLogFilter(logging.Filter):
            def filter(self, record):
                if record.levelno >= logging.INFO:
                    debug_logs.append(f"{record.levelname}: {record.getMessage()}")
                return True
                
        debug_handler.addFilter(DebugLogFilter())
        logging.getLogger("worker.sources.custom").addHandler(debug_handler)
        
        # 确保源ID以custom-开头
        source_id = source_data.get("id", f"custom-{random.randint(1000, 9999)}")
        if not source_id.startswith("custom-"):
            source_id = f"custom-{source_id}"
            
        logger.info(f"测试自定义源: {source_id}")
        
        # 使用工厂方法创建自定义源实例
        from worker.sources.factory import NewsSourceFactory
        
        config = {
            "selectors": source_data.get("selectors", {}),
            "use_selenium": bool(source_data.get("use_selenium", False)),
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": source_data.get("language", "en") + ",en-US;q=0.8,en;q=0.5",
                "Connection": "keep-alive"
            }
        }
        
        # 添加代理设置到配置
        if source_data.get("need_proxy", False):
            config["need_proxy"] = True
            config["proxy_fallback"] = bool(source_data.get("proxy_fallback", True))
            config["proxy_group"] = source_data.get("proxy_group", "default")
        
        logger.info(f"测试自定义源，配置信息: use_selenium={config['use_selenium']}, need_proxy={config.get('need_proxy', False)}")
        
        source = NewsSourceFactory.create_source(
            source_type=source_id,
            name=source_data.get("name", "Custom Source"),
            url=source_data.get("url", ""),
            category=source_data.get("category", "news"),
            country=source_data.get("country", "US"),
            language=source_data.get("language", "en"),
            update_interval=source_data.get("update_interval", 1800),
            cache_ttl=source_data.get("cache_ttl", 900),
            config=config
        )
        
        if not source:
            raise Exception(f"创建源适配器失败: {source_id}")
            
        # 执行测试
        start_time = time.time()
        items = await source.fetch()
        elapsed_time = time.time() - start_time
        
        # 移除调试处理器
        logging.getLogger("worker.sources.custom").removeHandler(debug_handler)
        
        # 格式化返回的项目
        formatted_items = []
        for item in items[:5]:  # 只返回前5个项目
            if hasattr(item, 'dict'):
                formatted_items.append(item.dict())
            elif hasattr(item, 'to_dict'):
                formatted_items.append(item.to_dict())
            else:
                # 如果没有dict或to_dict方法，手动构建字典
                formatted_items.append({
                    "id": getattr(item, "id", ""),
                    "title": getattr(item, "title", ""),
                    "url": getattr(item, "url", ""),
                    "summary": getattr(item, "summary", ""),
                    "content": getattr(item, "content", ""),
                    "published_at": getattr(item, "published_at", "").isoformat() if hasattr(item, "published_at") and item.published_at else "",
                    "source_id": getattr(item, "source_id", ""),
                    "source_name": getattr(item, "source_name", "")
                })
        
        # 返回结果
        return {
            "success": True,
            "source_id": source.source_id,
            "source_name": source.name,
            "items_count": len(items),
            "elapsed_time": elapsed_time,
            "items": formatted_items,
            "debug_info": {
                "logs": debug_logs,
                "selectors": config.get("selectors", {}),
                "url": source_data.get("url", ""),
                "page_debug": getattr(source, 'page_debug', {}),
                "use_selenium": config.get("use_selenium", False)
            }
        }
        
    except Exception as e:
        import traceback
        logger.error(f"测试自定义源时出错: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
    finally:
        # 确保释放源的资源
        if source and hasattr(source, 'close'):
            try:
                await source.close()
                logger.info(f"已关闭自定义源: {source.source_id}")
            except Exception as e:
                logger.error(f"关闭自定义源时出错: {str(e)}") 