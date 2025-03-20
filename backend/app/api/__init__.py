from fastapi import APIRouter

# 先定义路由器
api_router = APIRouter()

# 导入 endpoints 目录下的API模块
from app.api.endpoints import (
    news, 
    sources, 
    users, 
    auth, 
    tags, 
    categories, 
    external, 
    monitor,
    health
)

# 注册路由
api_router.include_router(monitor.router, prefix="/monitor", tags=["monitor"])
api_router.include_router(health.router, prefix="/health", tags=["system"])

# 注册endpoints目录下的路由
api_router.include_router(news.router, prefix="/news", tags=["news"])
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(tags.router, prefix="/tags", tags=["tags"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(external.router, prefix="/external", tags=["external"])