import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import sys
import logging
import atexit
import signal
import psutil
import time
import platform
from datetime import datetime
from fastapi.responses import RedirectResponse, FileResponse

# 添加当前目录到 Python 路径，确保可以正确导入模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Add parent directory to path to ensure worker module is found
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# 修改导入路径
from app.api import api_router
from app.core.config import settings
from app.core.logging_config import configure_logging

# 配置日志
configure_logging()
logger = logging.getLogger(__name__)

def find_and_kill_chrome_processes():
    """查找并杀死所有Chrome进程，尤其是Selenium启动的进程"""
    try:
        chrome_processes = []
        chromedriver_processes = []
        zombie_processes = []
        
        for process in psutil.process_iter(['pid', 'name', 'cmdline', 'status']):
            try:
                # 检查进程名是否包含chrome或chromium
                if process.info['name'] and ('chrome' in process.info['name'].lower() or 'chromium' in process.info['name'].lower()):
                    # 1. 检查是否为由Python脚本启动的Chrome (通过检查命令行参数中是否包含"--remote-debugging-port")
                    if process.info['cmdline'] and any('--remote-debugging-port' in arg for arg in process.info['cmdline']):
                        chrome_processes.append(process)
                    # 2. 检查是否为僵尸进程
                    elif process.info['status'] == 'zombie':
                        zombie_processes.append(process)
                    # 3. 检查是否为无头模式Chrome
                    elif process.info['cmdline'] and any('--headless' in arg for arg in process.info['cmdline']):
                        chrome_processes.append(process)
                        
                # 检查是否为ChromeDriver进程
                elif process.info['name'] and 'chromedriver' in process.info['name'].lower():
                    chromedriver_processes.append(process)
                # 检查是否为ChromeDriver (通过命令行参数)
                elif process.info['cmdline'] and any('chromedriver' in arg.lower() for arg in process.info['cmdline']):
                    chromedriver_processes.append(process)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        # 按顺序处理：先是Chrome进程，然后是ChromeDriver进程，最后是僵尸进程
        # 杀死找到的Chrome进程
        for process in chrome_processes:
            try:
                process.terminate()
                logger.info(f"已终止Chrome进程 (PID: {process.pid})")
            except Exception as e:
                logger.error(f"终止Chrome进程 (PID: {process.pid}) 失败: {str(e)}")
                try:
                    # 如果无法正常终止，尝试强制结束
                    process.kill()
                    logger.info(f"已强制结束Chrome进程 (PID: {process.pid})")
                except Exception as e:
                    logger.error(f"强制结束Chrome进程 (PID: {process.pid}) 失败: {str(e)}")
        
        # 杀死找到的ChromeDriver进程
        for process in chromedriver_processes:
            try:
                # 获取子进程
                children = process.children(recursive=True)
                # 先终止子进程
                for child in children:
                    try:
                        child.terminate()
                        logger.info(f"已终止ChromeDriver子进程 (PID: {child.pid})")
                    except Exception:
                        try:
                            child.kill()
                            logger.info(f"已强制结束ChromeDriver子进程 (PID: {child.pid})")
                        except Exception as e:
                            logger.error(f"强制结束ChromeDriver子进程 (PID: {child.pid}) 失败: {str(e)}")
                
                # 然后终止ChromeDriver进程
                process.terminate()
                logger.info(f"已终止ChromeDriver进程 (PID: {process.pid})")
            except Exception as e:
                logger.error(f"终止ChromeDriver进程 (PID: {process.pid}) 失败: {str(e)}")
                try:
                    # 如果无法正常终止，尝试强制结束
                    process.kill()
                    logger.info(f"已强制结束ChromeDriver进程 (PID: {process.pid})")
                except Exception as e:
                    logger.error(f"强制结束ChromeDriver进程 (PID: {process.pid}) 失败: {str(e)}")
        
        # 处理僵尸进程
        for process in zombie_processes:
            try:
                # 尝试查找并终止僵尸进程的父进程
                try:
                    parent = psutil.Process(process.ppid())
                    parent.terminate()
                    logger.info(f"已终止僵尸进程的父进程 (PID: {parent.pid})")
                except Exception:
                    pass
                
                # 尝试kill僵尸进程本身
                process.kill()
                logger.info(f"已尝试强制结束僵尸进程 (PID: {process.pid})")
            except Exception as e:
                logger.error(f"处理僵尸进程 (PID: {process.pid}) 失败: {str(e)}")
                    
        # 等待进程实际终止
        all_processes = chrome_processes + chromedriver_processes + zombie_processes
        gone, still_alive = psutil.wait_procs(all_processes, timeout=3)
        for process in still_alive:
            try:
                process.kill()
                logger.info(f"强制结束未响应的进程 (PID: {process.pid})")
            except Exception as e:
                logger.error(f"无法强制结束进程 (PID: {process.pid}): {str(e)}")
                
        return len(all_processes)
    except ImportError:
        logger.error("未安装psutil模块，无法查找和杀死Chrome进程")
        return 0
    except Exception as e:
        logger.error(f"查找和杀死Chrome进程时出错: {str(e)}")
        return 0

# 添加定期清理Chrome进程的函数
async def schedule_chrome_process_cleanup():
    """定期清理Chrome进程"""
    import asyncio
    from datetime import datetime
    
    # 清理间隔（秒）
    CLEANUP_INTERVAL = 3600  # 1小时
    
    while True:
        try:
            # 获取当前时间
            now = datetime.now()
            logger.info(f"开始定期清理Chrome进程 [{now.strftime('%Y-%m-%d %H:%M:%S')}]")
            
            # 执行清理
            chrome_count = find_and_kill_chrome_processes()
            if chrome_count > 0:
                logger.info(f"定期任务清理了 {chrome_count} 个Chrome相关进程")
            else:
                logger.info("没有找到需要清理的Chrome进程")
                
            # 等待下一次清理
            await asyncio.sleep(CLEANUP_INTERVAL)
        except Exception as e:
            logger.error(f"定期清理Chrome进程时出错: {str(e)}")
            # 出错后等待一段时间再重试
            await asyncio.sleep(300)  # 5分钟

app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Set up CORS
logger.info(f"配置CORS：{'允许所有来源' if '*' in settings.cors_origins else f'允许来源: {settings.cors_origins}'}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api")

# Mount static files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "static")
if os.path.exists(static_dir):
    # 单独挂载docs目录以确保index.html被正确处理
    docs_static_dir = os.path.join(static_dir, "docs")
    if os.path.exists(docs_static_dir):
        # 先挂载更具体的路径
        app.mount("/static/docs", StaticFiles(directory=docs_static_dir, html=True), name="docs_static")
        logger.info(f"Documentation mounted at /static/docs with HTML mode enabled")
        
        # 添加一个直接处理/static/docs/路径的路由
        @app.get("/static/docs/", include_in_schema=False)
        async def serve_docs_index():
            """直接提供docs/index.html文件"""
            index_path = os.path.join(docs_static_dir, "index.html")
            if os.path.exists(index_path):
                logger.info(f"Directly serving docs index.html from {index_path}")
                return FileResponse(index_path)
            return {"error": "Documentation index file not found"}
    
    # 然后挂载整个静态文件目录
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 添加一个路由专门处理/static/docs/路径
# @app.get("/static/docs", include_in_schema=False)
# @app.get("/static/docs/", include_in_schema=False)
# async def serve_docs_index():
#     """为/static/docs和/static/docs/路径提供index.html文件"""
#     index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "static", "docs", "index.html")
#     logger.info(f"Serving docs index.html from {index_path}")
#     return FileResponse(index_path)

# 不再需要自定义的docs挂载，因为已经包含在static目录中了

# Add a documentation redirect route
@app.get("/documentation", include_in_schema=False)
def documentation_redirect():
    """Redirect /documentation to the documentation center"""
    return RedirectResponse(url="/static/docs_index.html")

# 添加对/docs路径的重定向，以便兼容旧链接
@app.get("/docs", include_in_schema=False)
@app.get("/docs/{path:path}", include_in_schema=False)
async def docs_redirect(path: str = ""):
    """重定向旧的/docs路径到新的/static/docs路径"""
    redirect_url = "/static/docs/"
    
    # 如果有路径，添加到URL中
    if path:
        redirect_url = f"/static/docs/{path}"
    
    logger.info(f"Redirecting /docs/{path} to {redirect_url}")
    return RedirectResponse(url=redirect_url, status_code=302)

@app.get("/", include_in_schema=False)
def root():
    """重定向根路径到文档中心"""
    return RedirectResponse(url="/static/docs_index.html")

@app.get("/api-info", include_in_schema=True)
def api_info():
    """返回API信息和链接"""
    # 检查docs目录是否存在
    docs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "static", "docs")
    docs_exists = os.path.exists(docs_dir)
    
    response = {
        "message": f"Welcome to {settings.APP_NAME} API",
        "version": settings.APP_VERSION,
        "api_docs": "/api/docs",
        "documentation": "/documentation",  # 文档中心链接
        "source_test_ui": "/static/source_test.html",
        "format_checker_ui": "/static/format_checker.html",
        "source_monitor_ui": "/static/source_monitor.html",
        "source_monitor_simple_ui": "/static/source_monitor_simple.html",
    }
    
    # 如果文档目录存在，添加文档链接
    if docs_exists:
        response["project_docs"] = "/static/docs/"
        response["project_docs_search"] = "/static/docs/#/?search="
    
    return response

# 添加根级别的健康检查API
@app.get("/health")
def root_health():
    """
    根级别的健康检查端点
    简单返回API服务状态和基本性能指标
    """
    # 获取进程启动时间
    process = psutil.Process()
    start_time = datetime.fromtimestamp(process.create_time()).isoformat()
    
    # 获取系统信息
    system_info = {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "memory_usage_percent": psutil.virtual_memory().percent,
        "cpu_usage_percent": psutil.cpu_percent(interval=0.1)
    }
    
    return {
        "status": "ok",
        "api": "running",
        "message": "API service is operational",
        "timestamp": datetime.now().isoformat(),
        "process_start_time": start_time,
        "uptime_seconds": time.time() - process.create_time(),
        "system_info": system_info
    }

# 添加一个静态文件目录检查端点
@app.get("/debug/static-files", include_in_schema=True)
def debug_static_files():
    """返回静态文件目录的信息，用于调试"""
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "static")
    docs_dir = os.path.join(static_dir, "docs")
    
    # 检查静态文件目录
    static_exists = os.path.exists(static_dir)
    static_is_dir = os.path.isdir(static_dir) if static_exists else False
    static_files = os.listdir(static_dir) if static_is_dir else []
    
    # 检查文档目录
    docs_exists = os.path.exists(docs_dir)
    docs_is_dir = os.path.isdir(docs_dir) if docs_exists else False
    docs_files = os.listdir(docs_dir) if docs_is_dir else []
    
    # 检查index文件
    docs_index_html_path = os.path.join(docs_dir, "index.html")
    docs_index_html_exists = os.path.exists(docs_index_html_path)
    docs_index_html_size = os.path.getsize(docs_index_html_path) if docs_index_html_exists else 0
    
    # 检查sidebar文件
    docs_sidebar_path = os.path.join(docs_dir, "_sidebar.md")
    docs_sidebar_exists = os.path.exists(docs_sidebar_path)
    
    return {
        "static_directory": {
            "path": static_dir,
            "exists": static_exists,
            "is_directory": static_is_dir,
            "files": static_files[:10],  # 只返回前10个文件，避免响应过大
            "file_count": len(static_files)
        },
        "docs_directory": {
            "path": docs_dir,
            "exists": docs_exists,
            "is_directory": docs_is_dir,
            "files": docs_files[:10],  # 只返回前10个文件
            "file_count": len(docs_files)
        },
        "index_html": {
            "path": docs_index_html_path,
            "exists": docs_index_html_exists,
            "size_bytes": docs_index_html_size
        },
        "sidebar": {
            "path": docs_sidebar_path,
            "exists": docs_sidebar_exists
        }
    }

@app.on_event("startup")
async def startup_event():
    """应用启动时执行的事件处理器"""
    logger.info("应用启动，初始化数据源...")
    
    try:
        # 清理遗留的Chrome进程
        chrome_count = find_and_kill_chrome_processes()
        if chrome_count > 0:
            logger.info(f"已清理 {chrome_count} 个遗留的Chrome进程")
        
        # 导入需要的模块
        from worker.stats_wrapper import stats_updater
        from worker.sources.provider import DefaultNewsSourceProvider
        
        # 创建全局新闻源提供者
        source_provider = DefaultNewsSourceProvider()
        
        # 初始化统计信息更新器
        # 每5分钟更新一次统计信息，以获得更及时的数据
        stats_updater.enabled = True
        stats_updater.update_interval = 300  # 设置为5分钟
        logger.info("已初始化源统计信息自动更新器 (更新间隔: 5分钟)")
        
        # 获取所有可用的数据源
        sources = source_provider.get_all_sources()
        
        # 收集所有源类型ID并排序
        source_ids = sorted([source.source_id for source in sources])
        
        # 输出数据源类型列表
        logger.info(f"加载了 {len(source_ids)} 个数据源:")
        
        # 按字母顺序排序并分组输出，每行10个
        for i in range(0, len(source_ids), 10):
            chunk = source_ids[i:i+10]
            logger.info(", ".join(chunk))
        
        logger.info(f"已注册 {len(sources)} 个新闻源")
        
        # 设置全局访问点
        # 注意: 这里使用app.state存储提供者，以便其他模块可以访问
        app.state.source_provider = source_provider
        
        # 将source_provider中的所有源注册到source_manager中，确保API路由可以访问
        from worker.sources.manager import source_manager
        # 清空source_manager以避免重复
        source_manager.sources.clear()
        for source in sources:
            source_manager.register_source(source)
        logger.info(f"已将 {len(sources)} 个源从source_provider同步到source_manager")
        
        # 启动定期清理Chrome进程的任务
        import asyncio
        asyncio.create_task(schedule_chrome_process_cleanup())
        logger.info("已启动Chrome进程定期清理任务")
    except Exception as e:
        logger.error(f"初始化数据源时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行的事件处理器"""
    logger.info("应用关闭，清理资源...")
    
    try:
        # 导入统计信息更新器
        from worker.stats_wrapper import stats_updater
        
        # 禁用统计信息更新器，防止新的更新
        stats_updater.enabled = False
        logger.info("已禁用源统计信息自动更新器")
        
        # 关闭可能的Redis连接
        try:
            from worker.cache import cache_manager
            if hasattr(cache_manager, 'close') and callable(cache_manager.close):
                await cache_manager.close()
                logger.info("缓存连接已关闭")
        except Exception as e:
            logger.error(f"关闭缓存连接时出错: {str(e)}")
        
        # 清理所有Chrome进程
        chrome_count = find_and_kill_chrome_processes()
        if chrome_count > 0:
            logger.info(f"已清理 {chrome_count} 个Chrome进程")
        
        logger.info("所有资源已清理完毕")
    except Exception as e:
        logger.error(f"清理资源时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

# 注册退出处理函数
atexit.register(lambda: find_and_kill_chrome_processes())

# 设置信号处理器
def signal_handler(signum, frame):
    """信号处理器，用于捕获终止信号并执行清理操作"""
    logger.info(f"收到信号 {signum}，开始清理资源...")
    
    # 清理Chrome进程
    try:
        find_and_kill_chrome_processes()
        logger.info("已清理Chrome进程")
    except Exception as e:
        logger.error(f"清理Chrome进程时出错: {str(e)}")
    
    # 正常退出，不使用sys.exit(0)引发额外的异常
    logger.info("准备退出...")
    
    # 使用os._exit替代sys.exit，避免引发额外的异常
    import os
    os._exit(0)

# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # 终止信号

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 