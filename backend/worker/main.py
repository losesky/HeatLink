import os
import sys
import logging
import asyncio
import argparse
from typing import Dict, Any, Optional

from aiohttp import web
import aiohttp_cors

from worker.cache import CacheManager
from worker.scheduler import AdaptiveScheduler
from worker.sources.factory import NewsSourceFactory
from worker.sources.provider import DefaultNewsSourceProvider, NewsSourceProvider

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class NewsWorker:
    """
    新闻工作器
    负责启动调度器和API服务
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        enable_memory_cache: bool = True,
        enable_adaptive: bool = True,
        min_interval: int = 120,
        max_interval: int = 3600,
        api_host: str = "0.0.0.0",
        api_port: int = 8000,
        enable_cors: bool = True,
        use_api_for_data: bool = False,  # 是否使用API获取数据
        api_base_url: str = "http://localhost:8000"  # API基础URL
    ):
        self.redis_url = redis_url
        self.enable_memory_cache = enable_memory_cache
        self.enable_adaptive = enable_adaptive
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.api_host = api_host
        self.api_port = api_port
        self.enable_cors = enable_cors
        self.use_api_for_data = use_api_for_data
        self.api_base_url = api_base_url
        
        # 创建源提供者
        self.source_provider = DefaultNewsSourceProvider()
        
        # 创建缓存管理器
        self.cache_manager = CacheManager(
            redis_url=redis_url,
            enable_memory_cache=enable_memory_cache
        )
        
        # 创建调度器
        self.scheduler = AdaptiveScheduler(
            source_provider=self.source_provider,  # 传递源提供者
            cache_manager=self.cache_manager,
            min_interval=min_interval,
            max_interval=max_interval,
            enable_adaptive=enable_adaptive,
            api_base_url=self.api_base_url if self.use_api_for_data else None
        )
        
        # 创建API服务
        self.app = web.Application()
        
        # 注册路由
        self.app.add_routes([
            web.get("/", self.handle_index),
            web.get("/api/sources", self.handle_sources),
            web.get("/api/sources/{source_id}", self.handle_source),
            web.get("/api/news", self.handle_news),
            web.get("/api/news/{source_id}", self.handle_source_news),
            web.post("/api/refresh", self.handle_refresh),
            web.post("/api/refresh/{source_id}", self.handle_refresh_source),
            web.get("/api/status", self.handle_status),
            web.get("/api/cache/stats", self.handle_cache_stats),
            web.post("/api/cache/clear", self.handle_cache_clear)
        ])
        
        # 如果启用CORS，则配置CORS
        if enable_cors:
            cors = aiohttp_cors.setup(self.app, defaults={
                "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*"
                )
            })
            
            # 为所有路由配置CORS
            for route in list(self.app.router.routes()):
                cors.add(route)
        
        # 调度器任务
        self.scheduler_task = None
    
    async def start(self):
        """
        启动工作器
        """
        # 初始化缓存管理器
        await self.cache_manager.initialize()
        
        # 初始化调度器
        await self.scheduler.initialize()
        
        # 启动调度器任务
        self.scheduler_task = asyncio.create_task(self.scheduler.run_forever())
        
        # 启动API服务
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.api_host, self.api_port)
        await site.start()
        
        logger.info(f"API server started at http://{self.api_host}:{self.api_port}")
        
        # 等待调度器任务完成
        try:
            await self.scheduler_task
        except asyncio.CancelledError:
            logger.info("Scheduler task cancelled")
        finally:
            # 关闭API服务
            await runner.cleanup()
            
            # 关闭缓存管理器
            await self.cache_manager.close()
    
    async def stop(self):
        """
        停止工作器
        """
        # 取消调度器任务
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
            self.scheduler_task = None
    
    async def handle_index(self, request: web.Request) -> web.Response:
        """
        处理首页请求
        """
        return web.json_response({
            "name": "HeatLink News Worker",
            "version": "1.0.0",
            "status": "running"
        })
    
    async def handle_sources(self, request: web.Request) -> web.Response:
        """
        处理获取所有数据源请求
        """
        sources = self.scheduler.get_all_sources()
        
        # 转换为JSON格式
        result = []
        for source in sources:
            result.append({
                "id": source.source_id,
                "name": source.name,
                "category": source.category,
                "country": source.country,
                "language": source.language,
                "update_interval": source.update_interval
            })
        
        return web.json_response(result)
    
    async def handle_source(self, request: web.Request) -> web.Response:
        """
        处理获取单个数据源请求
        """
        source_id = request.match_info["source_id"]
        source = self.scheduler.get_source(source_id)
        
        if not source:
            return web.json_response({"error": f"Source not found: {source_id}"}, status=404)
        
        # 获取数据源状态
        status = self.scheduler.get_status()
        source_status = None
        for s in status["sources"]:
            if s["id"] == source_id:
                source_status = s
                break
        
        # 转换为JSON格式
        result = {
            "id": source.source_id,
            "name": source.name,
            "category": source.category,
            "country": source.country,
            "language": source.language,
            "update_interval": source.update_interval,
            "status": source_status
        }
        
        return web.json_response(result)
    
    async def handle_news(self, request: web.Request) -> web.Response:
        """
        处理获取所有新闻请求
        """
        # 获取查询参数
        category = request.query.get("category")
        country = request.query.get("country")
        language = request.query.get("language")
        limit = int(request.query.get("limit", "50"))
        
        # 获取所有数据源
        sources = self.scheduler.get_all_sources()
        
        # 过滤数据源
        if category:
            sources = [s for s in sources if s.category == category]
        if country:
            sources = [s for s in sources if s.country == country]
        if language:
            sources = [s for s in sources if s.language == language]
        
        # 获取所有新闻
        all_news = []
        for source in sources:
            try:
                # 从缓存获取数据
                cache_key = f"source:{source.source_id}"
                news_items = await self.cache_manager.get(cache_key)
                
                if news_items:
                    # 添加数据源信息
                    for item in news_items:
                        if not hasattr(item, "extra"):
                            item.extra = {}
                        item.extra["source_id"] = source.source_id
                        item.extra["source_name"] = source.name
                    
                    all_news.extend(news_items)
            except Exception as e:
                logger.error(f"Error getting news from source {source.source_id}: {str(e)}")
        
        # 按发布时间排序
        all_news.sort(key=lambda x: x.published_at if hasattr(x, "published_at") and x.published_at else 0, reverse=True)
        
        # 限制数量
        all_news = all_news[:limit]
        
        # 转换为JSON格式
        result = []
        for item in all_news:
            result.append(item.dict())
        
        return web.json_response(result)
    
    async def handle_source_news(self, request: web.Request) -> web.Response:
        """
        处理获取单个数据源新闻请求
        """
        source_id = request.match_info["source_id"]
        source = self.scheduler.get_source(source_id)
        
        if not source:
            return web.json_response({"error": f"Source not found: {source_id}"}, status=404)
        
        # 获取查询参数
        force = request.query.get("force") == "true"
        
        # 从缓存获取数据
        cache_key = f"source:{source_id}"
        news_items = await self.cache_manager.get(cache_key)
        
        # 如果强制刷新或缓存中没有数据，则抓取数据
        if force or not news_items:
            # 抓取数据
            success = await self.scheduler.fetch_source(source_id, force=True)
            
            if success:
                # 重新从缓存获取数据
                news_items = await self.cache_manager.get(cache_key)
            else:
                return web.json_response({"error": f"Failed to fetch data from source: {source_id}"}, status=500)
        
        # 如果仍然没有数据，则返回空列表
        if not news_items:
            return web.json_response([])
        
        # 转换为JSON格式
        result = []
        for item in news_items:
            result.append(item.dict())
        
        return web.json_response(result)
    
    async def handle_refresh(self, request: web.Request) -> web.Response:
        """
        处理刷新所有数据源请求
        """
        # 运行一次调度
        await self.scheduler.run_once(force=True)
        
        return web.json_response({"status": "success"})
    
    async def handle_refresh_source(self, request: web.Request) -> web.Response:
        """
        处理刷新单个数据源请求
        """
        source_id = request.match_info["source_id"]
        source = self.scheduler.get_source(source_id)
        
        if not source:
            return web.json_response({"error": f"Source not found: {source_id}"}, status=404)
        
        # 抓取数据
        success = await self.scheduler.fetch_source(source_id, force=True)
        
        if success:
            return web.json_response({"status": "success"})
        else:
            return web.json_response({"error": f"Failed to fetch data from source: {source_id}"}, status=500)
    
    async def handle_status(self, request: web.Request) -> web.Response:
        """
        处理获取状态请求
        """
        status = self.scheduler.get_status()
        return web.json_response(status)
    
    async def handle_cache_stats(self, request: web.Request) -> web.Response:
        """
        处理获取缓存统计信息请求
        """
        stats = await self.cache_manager.get_stats()
        return web.json_response(stats)
    
    async def handle_cache_clear(self, request: web.Request) -> web.Response:
        """
        处理清空缓存请求
        """
        # 获取查询参数
        pattern = request.query.get("pattern", "*")
        
        # 清空缓存
        await self.cache_manager.clear(pattern)
        
        return web.json_response({"status": "success"})


async def main():
    """
    主函数
    """
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="HeatLink News Worker")
    parser.add_argument("--redis-url", help="Redis URL", default=os.environ.get("REDIS_URL"))
    parser.add_argument("--no-memory-cache", help="Disable memory cache", action="store_true")
    parser.add_argument("--no-adaptive", help="Disable adaptive scheduling", action="store_true")
    parser.add_argument("--min-interval", help="Minimum fetch interval in seconds", type=int, default=120)
    parser.add_argument("--max-interval", help="Maximum fetch interval in seconds", type=int, default=3600)
    parser.add_argument("--host", help="API server host", default="0.0.0.0")
    parser.add_argument("--port", help="API server port", type=int, default=8000)
    parser.add_argument("--no-cors", help="Disable CORS", action="store_true")
    parser.add_argument("--use-api", help="Use API to fetch data instead of direct fetch", action="store_true")
    parser.add_argument("--api-base-url", help="API base URL", default="http://localhost:8000")
    
    args = parser.parse_args()
    
    # 创建工作器
    worker = NewsWorker(
        redis_url=args.redis_url,
        enable_memory_cache=not args.no_memory_cache,
        enable_adaptive=not args.no_adaptive,
        min_interval=args.min_interval,
        max_interval=args.max_interval,
        api_host=args.host,
        api_port=args.port,
        enable_cors=not args.no_cors,
        use_api_for_data=args.use_api,
        api_base_url=args.api_base_url
    )
    
    # 启动工作器
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, stopping worker")
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main()) 