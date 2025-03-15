from fastapi import APIRouter

from app.api.endpoints import auth, sources, news, categories, tags, users

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(news.router, prefix="/news", tags=["news"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(tags.router, prefix="/tags", tags=["tags"])
api_router.include_router(users.router, prefix="/users", tags=["users"]) 