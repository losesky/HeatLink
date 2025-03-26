import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import functools
import inspect

from sqlalchemy.orm import Session
from celery import Task

from app.crud.news import get_news_by_original_id, create_news, update_news
from app.crud.source import get_source, update_source
from app.db.session import SessionLocal
from app.models.news import News
from app.schemas.news import NewsCreate, NewsUpdate
from worker.celery_app import celery_app
from worker.sources.registry import source_registry
from worker.sources.base import NewsItemModel
from celery.utils.log import get_task_logger
from app.core.config import settings
from worker.sources.manager import source_manager
from worker.sources.interface import NewsSourceInterface
from worker.sources.provider import NewsSourceProvider, DefaultNewsSourceProvider
import random
import time
import traceback
import uuid

# 创建日志器
logger = logging.getLogger(__name__)

# 创建一个简单的ensure_event_loop装饰器，防止导入失败
def get_or_create_eventloop():
    """获取当前事件循环或创建新的事件循环"""
    try:
        return asyncio.get_event_loop()
    except RuntimeError as ex:
        if "There is no current event loop in thread" in str(ex):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop
        raise

def run_async(coro):
    """安全地运行异步协程"""
    loop = get_or_create_eventloop()
    return loop.run_until_complete(coro)

def ensure_event_loop(func):
    """确保异步函数在有效的事件循环中执行"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # 确保事件循环有效
        get_or_create_eventloop()
        try:
            return await func(*args, **kwargs)
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                logger.warning(f"检测到事件循环已关闭，为函数 {func.__name__} 创建新循环")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return await func(*args, **kwargs)
            raise
    return wrapper

# 尝试导入事件循环修复模块
try:
    from backend.worker.asyncio_fix import ensure_event_loop, run_async, get_or_create_eventloop
    have_asyncio_fix = True
    logger.info("成功从 backend.worker.asyncio_fix 导入事件循环修复")
except ImportError:
    try:
        from worker.asyncio_fix import ensure_event_loop, run_async, get_or_create_eventloop
        have_asyncio_fix = True
        logger.info("成功从 worker.asyncio_fix 导入事件循环修复")
    except ImportError:
        # 我们已经在上面定义了本地版本，所以继续使用它们
        have_asyncio_fix = True
        logger.warning("使用内置的事件循环修复函数")

# 尝试导入任务日志助手
try:
    from backend.worker.asyncio_fix.task_logger import log_task_execution, log_async_task_execution, add_task_step, complete_task_step, add_task_error, add_task_warning
    have_task_logger = True
except ImportError:
    try:
        from worker.asyncio_fix.task_logger import log_task_execution, log_async_task_execution, add_task_step, complete_task_step, add_task_error, add_task_warning
        have_task_logger = True
    except ImportError:
        have_task_logger = False

# 定义清理Chrome进程的函数
def cleanup_chrome_processes():
    """任务执行后清理Chrome进程"""
    try:
        # 导入清理函数
        try:
            # 尝试从backend.main导入
            from backend.main import find_and_kill_chrome_processes
        except ImportError:
            # 如果失败，尝试从main导入
            try:
                from main import find_and_kill_chrome_processes
            except ImportError:
                # 如果都失败，定义一个简化版的清理函数
                import psutil
                
                def find_and_kill_chrome_processes():
                    count = 0
                    for process in psutil.process_iter(['pid', 'name', 'cmdline']):
                        try:
                            # 检查Chrome和ChromeDriver进程
                            if (process.info['name'] and 
                                ('chrome' in process.info['name'].lower() or 
                                 'chromium' in process.info['name'].lower() or
                                 'chromedriver' in process.info['name'].lower())):
                                try:
                                    process.terminate()
                                    count += 1
                                except:
                                    try:
                                        process.kill()
                                        count += 1
                                    except:
                                        pass
                        except:
                            continue
                    return count
        
        # 执行清理
        count = find_and_kill_chrome_processes()
        if count > 0:
            logger.info(f"任务结束后清理了 {count} 个Chrome相关进程")
        
        return count
    except Exception as e:
        logger.error(f"清理Chrome进程时出错: {str(e)}")
        return 0

# 初始化全局新闻源提供者
source_provider = DefaultNewsSourceProvider()

# 从环境变量获取API配置
USE_API_FOR_DATA = os.environ.get("USE_API_FOR_DATA") == "1"
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

@celery_app.task(bind=True, name="news.schedule_source_updates")
def schedule_source_updates(self: Task) -> Dict[str, Any]:
    """
    检查并调度需要更新的源
    基于自适应调度器的结果决定哪些源需要更新
    """
    try:
        logger.info("Starting source update scheduler")
        
        # 使用异步函数来处理这个任务
        try:
            if have_asyncio_fix:
                # 使用安全的事件循环运行
                coroutine = _async_schedule_source_updates()
                results = run_async(coroutine)
            else:
                # 使用标准方法
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                coroutine = _async_schedule_source_updates()
                results = loop.run_until_complete(coroutine)
                loop.close()
                
            return results
        except Exception as e:
            logger.error(f"Error in async schedule source updates: {str(e)}")
            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"Error in source update scheduler: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        # 清理可能残留的Chrome进程
        cleanup_chrome_processes()

# 异步版本的调度任务
@ensure_event_loop
async def _async_schedule_source_updates() -> Dict[str, Any]:
    """
    异步版本的源更新调度器
    """
    # 获取所有源
    sources = source_provider.get_all_sources()
    
    scheduled_sources = []
    for source in sources:
        # 检查是否应该更新
        if source.should_update():
            # 创建异步任务，使用send_task而不是delay
            celery_app.send_task("news.fetch_source_news", args=[source.source_id])
            scheduled_sources.append(source.source_id)
    
    logger.info(f"Scheduled updates for {len(scheduled_sources)} sources")
    
    return {
        "status": "success",
        "message": f"Scheduled updates for {len(scheduled_sources)} sources",
        "sources": scheduled_sources
    }

@celery_app.task(bind=True, name="news.fetch_high_frequency_sources")
def fetch_high_frequency_sources(self: Task) -> Dict[str, Any]:
    """
    获取高频更新的新闻源（每10分钟）
    主要是社交媒体等实时性较强的源
    """
    try:
        logger.info("Starting high frequency news fetch task")
        
        # 获取所有高频更新的新闻源（更新间隔小于等于15分钟）
        sources = [
            source for source in source_manager.get_all_sources()
            if source.update_interval <= 900  # 15分钟 = 900秒
        ]
        
        if not sources:
            logger.info("No high frequency sources found")
            return {"status": "success", "message": "No high frequency sources found"}
        
        # 获取所有高频源的新闻
        try:
            if have_asyncio_fix:
                # 使用安全的事件循环运行
                coroutine = _fetch_sources_news(sources)
                results = run_async(coroutine)
            else:
                # 使用标准方法
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                coroutine = _fetch_sources_news(sources)
                results = loop.run_until_complete(coroutine)
                loop.close()
            
            # 确保结果可用并适合计算
            total_news = 0
            for source_id, news_list in results.items():
                if isinstance(news_list, list):
                    total_news += len(news_list)

            # 记录任务成功信息
            logger.info(f"Task news.fetch_high_frequency_sources succeeded: Fetched from {len(sources)} sources, saved {total_news} news")
            
            return {
                "status": "success",
                "message": f"Fetched news from {len(results)} high frequency sources",
                "sources": [source.source_id for source in sources],
                "total_news": total_news
            }
        except Exception as e:
            logger.error(f"Error in high frequency news fetch task: {str(e)}")
            return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"Error in high frequency news fetch task: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        # 清理可能残留的Chrome进程
        cleanup_chrome_processes()


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
        try:
            if have_asyncio_fix:
                # 使用安全的事件循环运行
                coroutine = _fetch_sources_news(sources)
                results = run_async(coroutine)
            else:
                # 使用标准方法
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                coroutine = _fetch_sources_news(sources)
                results = loop.run_until_complete(coroutine)
                loop.close()
            
            # 确保结果可用并适合计算
            total_news = 0
            for source_id, news_list in results.items():
                if isinstance(news_list, list):
                    total_news += len(news_list)

            # 记录任务成功信息
            logger.info(f"Task news.fetch_medium_frequency_sources succeeded: Fetched from {len(sources)} sources, saved {total_news} news")
            
            return {
                "status": "success",
                "message": f"Fetched news from {len(results)} medium frequency sources",
                "sources": [source.source_id for source in sources],
                "total_news": total_news
            }
        except Exception as e:
            logger.error(f"Error in medium frequency news fetch task: {str(e)}")
            return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"Error in medium frequency news fetch task: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        # 清理可能残留的Chrome进程
        cleanup_chrome_processes()


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
        try:
            if have_asyncio_fix:
                # 使用安全的事件循环运行
                coroutine = _fetch_sources_news(sources)
                results = run_async(coroutine)
            else:
                # 使用标准方法
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                coroutine = _fetch_sources_news(sources)
                results = loop.run_until_complete(coroutine)
                loop.close()
            
            # 确保结果可用并适合计算
            total_news = 0
            for source_id, news_list in results.items():
                if isinstance(news_list, list):
                    total_news += len(news_list)

            # 记录任务成功信息
            logger.info(f"Task news.fetch_low_frequency_sources succeeded: Fetched from {len(sources)} sources, saved {total_news} news")
            
            return {
                "status": "success",
                "message": f"Fetched news from {len(results)} low frequency sources",
                "sources": [source.source_id for source in sources],
                "total_news": total_news
            }
        except Exception as e:
            logger.error(f"Error in low frequency news fetch task: {str(e)}")
            return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"Error in low frequency news fetch task: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        # 清理可能残留的Chrome进程
        cleanup_chrome_processes()


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
        try:
            if have_asyncio_fix:
                # 使用安全的事件循环运行
                coroutine = _fetch_sources_news(sources)
                results = run_async(coroutine)
            else:
                # 使用标准方法
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                coroutine = _fetch_sources_news(sources)
                results = loop.run_until_complete(coroutine)
                loop.close()
            
            # 确保结果可用并适合计算
            total_news = 0
            for source_id, news_list in results.items():
                if isinstance(news_list, list):
                    total_news += len(news_list)
                    
            # 记录任务成功信息
            logger.info(f"Task news.fetch_all_news succeeded: Fetched from {len(sources)} sources, saved {total_news} news")
            
            return {
                "status": "success",
                "message": f"Fetched news from {len(results)} sources",
                "sources": [source.source_id for source in sources],
                "total_news": total_news
            }
        except Exception as e:
            logger.error(f"Error in fetch all news task: {str(e)}")
            return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"Error in fetch all news task: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        # 清理可能残留的Chrome进程
        cleanup_chrome_processes()


@celery_app.task(bind=True, name="news.fetch_source_news")
def fetch_source_news(self: Task, source_id: str) -> Dict[str, Any]:
    """
    获取指定新闻源的新闻
    
    Args:
        source_id: 新闻源ID
    """
    # 任务ID用于日志关联
    task_uuid = str(uuid.uuid4())
    
    # 使用任务日志助手
    if have_task_logger:
        from backend.worker.asyncio_fix.task_logger import set_task_context
        set_task_context(task_uuid, "news.fetch_source_news", {"source_id": source_id})
        add_task_step("task_initialization")
    
    try:
        logger.info(f"[{task_uuid}] 开始获取新闻源 {source_id} 的新闻")
        
        if have_task_logger:
            add_task_step("get_source_from_provider")
            
        # 从提供者获取新闻源
        source = source_provider.get_source(source_id)
        if not source:
            error_msg = f"未找到新闻源: {source_id}"
            logger.error(f"[{task_uuid}] {error_msg}")
            
            if have_task_logger:
                add_task_error(error_msg)
                complete_task_step("get_source_from_provider", "error", error_msg)
                
            return {
                "status": "error",
                "message": error_msg,
                "source_id": source_id,
                "count": 0,
                "task_id": task_uuid
            }
        
        if have_task_logger:
            complete_task_step("get_source_from_provider")
            add_task_step("fetch_news")
        
        # 获取新闻 - 使用带装饰器的版本
        coroutine = _fetch_source_news(source)
        
        try:
            if have_asyncio_fix:
                # 使用安全的事件循环运行
                try:
                    news_items = run_async(coroutine)
                except RuntimeError as e:
                    # 特别处理事件循环已关闭错误
                    if "Event loop is closed" in str(e):
                        logger.warning(f"[{task_uuid}] 检测到事件循环已关闭，正在尝试重新创建...")
                        # 强制创建新的事件循环
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        news_items = loop.run_until_complete(coroutine)
                        loop.close()
                    else:
                        raise
            else:
                # 使用标准方法
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    news_items = loop.run_until_complete(coroutine)
                finally:
                    loop.close()
        except Exception as e:
            error_msg = f"获取新闻源 {source_id} 时出错: {str(e)}"
            logger.error(f"[{task_uuid}] {error_msg}")
            logger.error(traceback.format_exc())
            
            if have_task_logger:
                add_task_error(error_msg, e)
                complete_task_step("fetch_news", "error", error_msg)
                
            # 返回错误信息
            return {
                "status": "error",
                "message": error_msg,
                "source_id": source_id,
                "count": 0,
                "error": str(e),
                "task_id": task_uuid
            }
        
        if have_task_logger:
            complete_task_step("fetch_news")
            add_task_step("process_results")
        
        # 计算结果
        count = len(news_items) if news_items else 0
        
        if have_task_logger:
            complete_task_step("process_results")
            add_task_step("save_to_database")
        
        # 存储到数据库
        try:
            saved_count = _save_news_to_db(news_items) if news_items else 0
        except Exception as e:
            error_msg = f"保存新闻到数据库时出错: {str(e)}"
            logger.error(f"[{task_uuid}] {error_msg}")
            logger.error(traceback.format_exc())
            
            if have_task_logger:
                add_task_error(error_msg, e)
                complete_task_step("save_to_database", "error", error_msg)
                
            # 即使保存失败，也返回获取的新闻数量
            return {
                "status": "partial_success",
                "message": f"获取了 {count} 条新闻，但保存到数据库时出错: {str(e)}",
                "source_id": source_id,
                "count": count,
                "saved_count": 0,
                "error": str(e),
                "task_id": task_uuid
            }
        
        if have_task_logger:
            complete_task_step("save_to_database")
            add_task_step("finalize")
        
        logger.info(f"[{task_uuid}] 从新闻源 {source_id} 获取了 {count} 条新闻，保存了 {saved_count} 条到数据库")
        
        if count > 0 and saved_count == 0:
            warning_msg = f"获取了 {count} 条新闻，但没有保存任何数据"
            logger.warning(f"[{task_uuid}] {warning_msg}")
            
            if have_task_logger:
                add_task_warning(warning_msg)
        
        if have_task_logger:
            complete_task_step("finalize")
            complete_task_step("task_initialization")
        
        # 返回结果
        return {
            "status": "success",
            "message": f"从新闻源 {source_id} 获取了 {count} 条新闻，保存了 {saved_count} 条到数据库",
            "source_id": source_id,
            "count": count,
            "saved_count": saved_count,
            "task_id": task_uuid
        }
        
    except Exception as e:
        error_msg = f"处理新闻源 {source_id} 时发生未预期的错误: {str(e)}"
        logger.error(f"[{task_uuid}] {error_msg}")
        logger.error(traceback.format_exc())
        
        if have_task_logger:
            add_task_error(error_msg, e)
        
        return {
            "status": "error",
            "message": error_msg,
            "source_id": source_id,
            "count": 0,
            "error": str(e),
            "task_id": task_uuid
        }

# 根据是否有asyncio修复模块，使用不同的实现
if have_asyncio_fix:
    # 事件循环修复版本
    @ensure_event_loop
    async def _fetch_sources_news(sources: List[Any]) -> Dict[str, List[Any]]:
        """
        获取多个源的新闻
        
        Args:
            sources: 源列表
            
        Returns:
            以源ID为键，新闻列表为值的字典
        """
        logger.info(f"Fetching news from {len(sources)} sources")
        
        results = {}
        tasks = []
        
        # 创建任务
        for source in sources:
            tasks.append(_fetch_source_news(source))
        
        # 并发执行任务
        try:
            source_news_list = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            for i, news_items in enumerate(source_news_list):
                source = sources[i]
                if isinstance(news_items, Exception):
                    logger.error(f"Error fetching news from {source.source_id}: {str(news_items)}")
                    continue
                
                # 保存到数据库
                saved_count = _save_news_to_db(news_items)
                
                # 更新源的最后更新时间
                db = SessionLocal()
                try:
                    # 获取源对象
                    db_source = get_source(db, source.source_id)
                    if db_source:
                        update_source(db, db_source, {"last_updated": datetime.now()})
                finally:
                    db.close()
                
                results[source.source_id] = news_items
                logger.info(f"Fetched {len(news_items)} news from {source.source_id}, saved {saved_count}")
        except Exception as e:
            logger.error(f"Error in async gather: {str(e)}")
        
        return results
    
    @ensure_event_loop
    async def _fetch_source_news(source: Any) -> List[Any]:
        """
        获取单个源的新闻
        
        Args:
            source: 新闻源
            
        Returns:
            新闻列表
        """
        logger.info(f"Fetching news for {source.source_id}")
        
        try:
            # 判断是否通过API获取数据
            if USE_API_FOR_DATA:
                # 通过API获取数据
                import aiohttp
                from worker.sources.base import NewsItemModel
                
                # 构建API URL
                url = f"{API_BASE_URL}/api/sources/external/{source.source_id}/news"
                
                logger.info(f"Fetching from API: {url}")
                
                # 发送请求
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"API error: {response.status} - {error_text}")
                            raise Exception(f"API error: {response.status} - {error_text}")
                        
                        # 解析响应
                        data = await response.json()
                        
                        # 将JSON数据转换为NewsItemModel对象
                        news_items = []
                        for item_data in data:
                            news_item = NewsItemModel.from_dict(item_data)
                            news_items.append(news_item)
                
                logger.info(f"API fetch completed for {source.source_id}, received {len(news_items)} items")
                return news_items
            else:
                # 直接从源获取数据，使用stats_updater.wrap_fetch包装获取internal API调用统计
                from worker.stats_wrapper import stats_updater
                original_fetch = source.fetch
                source.fetch = lambda *args, **kwargs: stats_updater.wrap_fetch(source.source_id, original_fetch, api_type="internal", *args, **kwargs)
                
                try:
                    # 获取新闻
                    news_items = await source.get_news()
                    logger.info(f"source.get_news completed for {source.source_id}, received {len(news_items)} items")
                    return news_items
                finally:
                    # 恢复原始fetch方法
                    source.fetch = original_fetch
        except Exception as e:
            logger.error(f"Error fetching news from {source.source_id}: {str(e)}")
            
            # 不再返回空列表，而是重新抛出异常
            # 这样调用者可以正确处理错误，同时允许stats_updater正确记录失败
            logger.warning(f"Source {source.source_id} failed to provide data: {str(e)}")
            # 为了保持向后兼容性，将异常包装成RuntimeError
            raise RuntimeError(f"Source {source.source_id} failed: {str(e)}")
else:
    # 标准版本，不使用事件循环装饰器
    async def _fetch_sources_news(sources: List[Any]) -> Dict[str, List[Any]]:
        """
        获取多个源的新闻
        
        Args:
            sources: 源列表
            
        Returns:
            以源ID为键，新闻列表为值的字典
        """
        logger.info(f"Fetching news from {len(sources)} sources")
        
        results = {}
        tasks = []
        
        # 创建任务
        for source in sources:
            tasks.append(_fetch_source_news(source))
        
        # 并发执行任务
        try:
            source_news_list = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            for i, news_items in enumerate(source_news_list):
                source = sources[i]
                if isinstance(news_items, Exception):
                    logger.error(f"Error fetching news from {source.source_id}: {str(news_items)}")
                    continue
                
                # 保存到数据库
                saved_count = _save_news_to_db(news_items)
                
                # 更新源的最后更新时间
                db = SessionLocal()
                try:
                    # 获取源对象
                    db_source = get_source(db, source.source_id)
                    if db_source:
                        update_source(db, db_source, {"last_updated": datetime.now()})
                finally:
                    db.close()
                
                results[source.source_id] = news_items
                logger.info(f"Fetched {len(news_items)} news from {source.source_id}, saved {saved_count}")
        except Exception as e:
            logger.error(f"Error in async gather: {str(e)}")
        
        return results
    
    async def _fetch_source_news(source: Any) -> List[Any]:
        """
        获取单个源的新闻
        
        Args:
            source: 新闻源
            
        Returns:
            新闻列表
        """
        logger.info(f"Fetching news for {source.source_id}")
        
        try:
            # 判断是否通过API获取数据
            if USE_API_FOR_DATA:
                # 通过API获取数据
                import aiohttp
                from worker.sources.base import NewsItemModel
                
                # 构建API URL
                url = f"{API_BASE_URL}/api/sources/external/{source.source_id}/news"
                
                logger.info(f"Fetching from API: {url}")
                
                # 发送请求
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"API error: {response.status} - {error_text}")
                            raise Exception(f"API error: {response.status} - {error_text}")
                        
                        # 解析响应
                        data = await response.json()
                        
                        # 将JSON数据转换为NewsItemModel对象
                        news_items = []
                        for item_data in data:
                            news_item = NewsItemModel.from_dict(item_data)
                            news_items.append(news_item)
                
                logger.info(f"API fetch completed for {source.source_id}, received {len(news_items)} items")
                return news_items
            else:
                # 直接从源获取数据，使用stats_updater.wrap_fetch包装获取internal API调用统计
                from worker.stats_wrapper import stats_updater
                original_fetch = source.fetch
                source.fetch = lambda *args, **kwargs: stats_updater.wrap_fetch(source.source_id, original_fetch, api_type="internal", *args, **kwargs)
                
                try:
                    # 获取新闻
                    news_items = await source.get_news()
                    logger.info(f"source.get_news completed for {source.source_id}, received {len(news_items)} items")
                    return news_items
                finally:
                    # 恢复原始fetch方法
                    source.fetch = original_fetch
        except Exception as e:
            logger.error(f"Error fetching news from {source.source_id}: {str(e)}")
            
            # 不再返回空列表，而是重新抛出异常
            # 这样调用者可以正确处理错误，同时允许stats_updater正确记录失败
            logger.warning(f"Source {source.source_id} failed to provide data: {str(e)}")
            # 为了保持向后兼容性，将异常包装成RuntimeError
            raise RuntimeError(f"Source {source.source_id} failed: {str(e)}")

def _save_news_to_db(news_items: List[Any]) -> int:
    """
    将新闻保存到数据库
    
    Args:
        news_items: 新闻列表
        
    Returns:
        保存的新闻数量
    """
    if not news_items:
        return 0
    
    db = SessionLocal()
    try:
        saved_count = 0
        for item in news_items:
            try:
                # 获取original_id，如果item有original_id属性则使用，否则使用id
                original_id = item.id
                if hasattr(item, 'original_id'):
                    original_id = item.original_id
                
                # 检查source_id是否为空，如果为空则跳过该条新闻
                if not item.source_id:
                    logger.warning(f"跳过保存新闻: {item.title} - source_id为空")
                    continue
                
                # 检查是否已存在 - 正确传递source_id和original_id两个参数
                existing_news = get_news_by_original_id(db, item.source_id, original_id)
                
                if existing_news:
                    # 更新现有新闻
                    update_data = NewsUpdate(
                        title=item.title,
                        content=item.content,
                        summary=item.summary,
                        url=item.url,
                        image_url=item.image_url,
                        published_at=item.published_at,
                        source_id=item.source_id,
                        category_id=item.category_id if hasattr(item, 'category_id') else None,
                    )
                    update_news(db, existing_news.id, update_data)
                else:
                    # 创建新新闻
                    news_data = NewsCreate(
                        title=item.title,
                        content=item.content,
                        summary=item.summary,
                        url=item.url,
                        image_url=item.image_url,
                        published_at=item.published_at,
                        source_id=item.source_id,
                        original_id=original_id,
                        category_id=item.category_id if hasattr(item, 'category_id') else None,
                    )
                    create_news(db, news_data)
                    saved_count += 1
            except Exception as e:
                logger.error(f"Error saving news item: {str(e)}")
                # 如果出现异常，进行回滚以避免事务被挂起
                db.rollback()
                continue
        
        return saved_count
    finally:
        db.close()


def init_sources():
    """
    初始化新闻源
    """
    # 注册默认新闻源
    source_manager.register_default_sources()
    logger.info("Initialized default news sources")

@celery_app.task(bind=True, name="news.cleanup_old_news")
def cleanup_old_news(self: Task, days: int = 30) -> Dict[str, Any]:
    """
    清理指定天数之前的旧新闻
    默认清理30天前的新闻
    """
    logger.info(f"Starting cleanup of news older than {days} days")
    
    try:
        # 计算截止日期
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # 创建数据库会话
        db = SessionLocal()
        try:
            # 查询需要删除的新闻数量
            query = db.query(News).filter(News.created_at < cutoff_date)
            count = query.count()
            
            if count == 0:
                logger.info(f"No news items older than {days} days found")
                return {
                    "status": "success",
                    "message": f"No news items older than {days} days found",
                    "deleted_count": 0
                }
            
            # 执行删除操作
            query.delete()
            db.commit()
            
            logger.info(f"Successfully deleted {count} news items older than {days} days")
            
            return {
                "status": "success",
                "message": f"Successfully deleted {count} news items older than {days} days",
                "deleted_count": count
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error cleaning up old news: {str(e)}")
        return {"status": "error", "message": str(e)}

@celery_app.task(bind=True, name="news.analyze_news_trends")
def analyze_news_trends(self: Task, days: int = 7) -> Dict[str, Any]:
    """
    分析新闻趋势和热点话题
    默认分析最近7天的新闻
    """
    logger.info(f"Starting news trend analysis for past {days} days")
    
    try:
        # 计算开始日期
        start_date = datetime.now() - timedelta(days=days)
        
        # 创建数据库会话
        db = SessionLocal()
        try:
            # 查询最近的新闻
            news_items = db.query(News).filter(News.created_at >= start_date).all()
            
            if not news_items:
                logger.info(f"No news items found in the past {days} days")
                return {
                    "status": "success",
                    "message": f"No news items found in the past {days} days",
                    "trends": []
                }
            
            # 这里只是一个简单的实现，实际项目中可以添加更复杂的趋势分析算法
            # 例如文本分析、聚类、热点检测等
            
            # 简单的源统计
            source_counts = {}
            for item in news_items:
                source_id = item.source_id
                if source_id in source_counts:
                    source_counts[source_id] += 1
                else:
                    source_counts[source_id] = 1
            
            # 排序获取热门源
            top_sources = sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            
            logger.info(f"Completed trend analysis for {len(news_items)} news items")
            
            return {
                "status": "success",
                "message": f"Analyzed trends for {len(news_items)} news items from the past {days} days",
                "total_items": len(news_items),
                "top_sources": top_sources
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error analyzing news trends: {str(e)}")
        return {"status": "error", "message": str(e)}

# 初始化新闻源
init_sources() 