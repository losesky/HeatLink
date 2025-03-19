from typing import Any, List, Dict, Optional
import asyncio
import logging
from datetime import datetime
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Path, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_superuser, get_current_active_superuser, get_current_active_user
from app.models.user import User
from app.crud import source as crud
from app.crud.source import (
    get_source, get_sources, create_source, update_source, delete_source,
    get_source_with_stats, create_source_alias, delete_source_alias
)
from app.models.source import SourceType
from app.schemas.source import (
    Source, SourceCreate, SourceUpdate, SourceWithStats,
    SourceAlias, SourceAliasCreate
)
from worker.sources.factory import NewsSourceFactory
from worker.sources.base import NewsSource, NewsItemModel

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("sources_api")

router = APIRouter()

# 辅助函数
async def close_source(source):
    """关闭新闻源并释放资源"""
    if source is None:
        return
    
    try:
        # 调用close方法
        if hasattr(source, 'close'):
            try:
                await source.close()
                return
            except Exception as e:
                logger.warning(f"Error calling close() method: {str(e)}")
        
        # 尝试关闭http_client
        if hasattr(source, '_http_client') and source._http_client is not None:
            if hasattr(source._http_client, 'close'):
                await source._http_client.close()
        
        # 尝试关闭aiohttp会话
        import aiohttp
        import inspect
        for attr_name in dir(source):
            if attr_name.startswith('_'):
                continue
                
            try:
                attr = getattr(source.__class__, attr_name, None)
                if attr and (inspect.iscoroutine(attr) or inspect.isawaitable(attr) or 
                           inspect.iscoroutinefunction(attr) or isinstance(attr, property)):
                    continue
                
                attr = getattr(source, attr_name)
                
                if isinstance(attr, aiohttp.ClientSession) and not attr.closed:
                    await attr.close()
            except (AttributeError, TypeError):
                pass
    except Exception as e:
        logger.warning(f"Error closing source: {str(e)}")


# 数据库管理API端点
@router.get("/", response_model=List[Source])
async def read_sources(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    """
    Retrieve sources with pagination.
    """
    sources = get_sources(db, skip=skip, limit=limit)
    processed_sources = []
    
    for source in sources:
        # Convert timedelta fields to integers
        source_dict = {}
        for key, value in source.__dict__.items():
            if key == "_sa_instance_state":
                continue
                
            # Handle timedelta fields
            if key == "update_interval" and hasattr(value, "total_seconds"):
                source_dict[key] = int(value.total_seconds())
            elif key == "cache_ttl" and hasattr(value, "total_seconds"):
                source_dict[key] = int(value.total_seconds())
            else:
                source_dict[key] = value
                
        # Ensure all required fields have valid values
        if "priority" not in source_dict or source_dict["priority"] is None:
            source_dict["priority"] = 0
        if "error_count" not in source_dict or source_dict["error_count"] is None:
            source_dict["error_count"] = 0
        if "news_count" not in source_dict or source_dict["news_count"] is None:
            source_dict["news_count"] = 0
        
        # Convert dictionary to Pydantic model and add to list
        processed_sources.append(Source.model_validate(source_dict))
    
    return processed_sources


@router.post("/", response_model=Source)
def create_new_source(
    *,
    db: Session = Depends(get_db),
    source_in: SourceCreate,
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    创建新闻源
    
    创建新的新闻源配置信息，需要超级用户权限
    """
    source = create_source(db=db, obj_in=source_in)
    return source


@router.get("/available", response_model=List[Source])
async def read_available_sources(
    db: Session = Depends(get_db),
):
    """
    Get available sources.
    
    返回系统中所有可用的新闻源适配器列表。这些是系统能够从中获取新闻的所有可能来源。
    注意：这与/api/sources/不同，后者返回数据库中已配置的源。
    """
    import traceback
    import sys
    
    logger.info("开始执行read_available_sources函数 - 获取所有可用新闻源")
    
    try:
        # 获取所有可用源类型
        logger.info("正在获取所有可用源类型...")
        source_types = NewsSourceFactory.get_available_sources()
        logger.info(f"成功获取到 {len(source_types)} 个源类型: {source_types}")
        
        # 硬编码的源类型列表作为备用
        hardcoded_source_types = [
            "zhihu", "baidu", "weibo", "bilibili", "toutiao", "douyin", "hacker_news", 
            "bbc_news", "bbc_world", "bloomberg", "bloomberg-markets", "bloomberg-tech", 
            "bloomberg-china", "v2ex", "github", "ithome", "coolapk", "coolapk-app", 
            "coolapk-feed", "cls", "cls-article", "jin10", "xueqiu", "tieba", "kuaishou", 
            "solidot", "zaobao", "thepaper-selenium", "sputniknewscn", "producthunt", 
            "linuxdo", "linuxdo-latest", "linuxdo-hot", "kaopu", "gelonghui", 
            "fastbull-express", "fastbull-news", "wallstreetcn", "wallstreetcn-news", 
            "wallstreetcn-hot", "36kr", "cankaoxiaoxi", "zhihu_daily", "ifanr", 
            "techcrunch", "the_verge"
        ]
        
        # 如果从工厂获取的类型少于预期，使用硬编码列表
        if len(source_types) < 45:
            logger.warning(f"从工厂获取的源类型数量 ({len(source_types)}) 少于预期的46个，将使用硬编码列表")
            if len(hardcoded_source_types) > len(source_types):
                source_types = hardcoded_source_types
                logger.info(f"切换到硬编码源类型列表，包含 {len(source_types)} 个源")
        
        # 创建一个列表存储Source对象
        sources = []
        
        # 源类型映射到人类可读的名称
        source_names = {
            "zhihu": "知乎热榜",
            "baidu": "百度热搜",
            "weibo": "微博热搜",
            "bilibili": "B站热搜",
            "toutiao": "今日头条热搜",
            "douyin": "抖音热搜",
            "hacker_news": "Hacker News",
            "bbc_news": "BBC News",
            "bbc_world": "BBC World News",
            "bloomberg": "彭博社",
            "bloomberg-markets": "彭博社市场",
            "bloomberg-tech": "彭博社科技",
            "bloomberg-china": "彭博社中国",
            "v2ex": "V2EX热门",
            "github": "GitHub Trending",
            "ithome": "IT之家",
            "coolapk": "酷安",
            "coolapk-app": "酷安应用",
            "coolapk-feed": "酷安动态",
            "cls": "财联社",
            "cls-article": "财联社文章",
            "jin10": "金十数据快讯",
            "xueqiu": "雪球热门股票",
            "tieba": "贴吧热门话题",
            "kuaishou": "快手热搜",
            "solidot": "奇客",
            "zaobao": "早报",
            "thepaper-selenium": "澎湃新闻热榜",
            "sputniknewscn": "卫星通讯社",
            "producthunt": "Product Hunt",
            "linuxdo": "Linux迷",
            "linuxdo-latest": "Linux迷最新",
            "linuxdo-hot": "Linux迷热门",
            "kaopu": "靠谱新闻",
            "gelonghui": "格隆汇",
            "fastbull-express": "快牛快讯",
            "fastbull-news": "快牛新闻",
            "wallstreetcn": "华尔街见闻快讯",
            "wallstreetcn-news": "华尔街见闻文章",
            "wallstreetcn-hot": "华尔街见闻热门",
            "36kr": "36氪快讯",
            "cankaoxiaoxi": "参考消息",
            "zhihu_daily": "知乎日报",
            "ifanr": "爱范儿",
            "techcrunch": "TechCrunch",
            "the_verge": "The Verge"
        }
        
        # 源类型映射到分类
        source_categories = {
            "zhihu": "social",
            "baidu": "social",
            "weibo": "social",
            "bilibili": "social",
            "toutiao": "news",
            "douyin": "social",
            "hacker_news": "tech",
            "bbc_news": "news",
            "bbc_world": "news",
            "bloomberg": "finance",
            "bloomberg-markets": "finance",
            "bloomberg-tech": "tech",
            "bloomberg-china": "finance",
            "v2ex": "forum",
            "github": "dev",
            "ithome": "tech",
            "coolapk": "tech",
            "coolapk-app": "tech",
            "coolapk-feed": "tech",
            "cls": "finance",
            "cls-article": "finance",
            "jin10": "finance",
            "xueqiu": "finance",
            "tieba": "forum",
            "kuaishou": "social",
            "solidot": "tech",
            "zaobao": "news",
            "thepaper-selenium": "news",
            "sputniknewscn": "news",
            "producthunt": "tech",
            "linuxdo": "tech",
            "linuxdo-latest": "tech",
            "linuxdo-hot": "tech",
            "kaopu": "news",
            "gelonghui": "finance",
            "fastbull-express": "finance",
            "fastbull-news": "finance",
            "wallstreetcn": "finance",
            "wallstreetcn-news": "finance",
            "wallstreetcn-hot": "finance",
            "36kr": "tech",
            "cankaoxiaoxi": "news",
            "zhihu_daily": "knowledge",
            "ifanr": "tech",
            "techcrunch": "tech",
            "the_verge": "tech"
        }
        
        # 源类型映射到国家
        source_countries = {
            "zhihu": "CN",
            "baidu": "CN",
            "weibo": "CN",
            "bilibili": "CN",
            "toutiao": "CN",
            "douyin": "CN",
            "hacker_news": "US",
            "bbc_news": "UK",
            "bbc_world": "UK",
            "bloomberg": "US",
            "bloomberg-markets": "US",
            "bloomberg-tech": "US",
            "bloomberg-china": "CN",
            "v2ex": "CN",
            "github": "US",
            "ithome": "CN",
            "coolapk": "CN",
            "coolapk-app": "CN",
            "coolapk-feed": "CN",
            "cls": "CN",
            "cls-article": "CN",
            "jin10": "CN",
            "xueqiu": "CN",
            "tieba": "CN",
            "kuaishou": "CN",
            "solidot": "CN",
            "zaobao": "SG",
            "thepaper-selenium": "CN",
            "sputniknewscn": "RU",
            "producthunt": "US",
            "linuxdo": "CN",
            "linuxdo-latest": "CN",
            "linuxdo-hot": "CN",
            "kaopu": "CN",
            "gelonghui": "CN",
            "fastbull-express": "CN",
            "fastbull-news": "CN",
            "wallstreetcn": "CN",
            "wallstreetcn-news": "CN",
            "wallstreetcn-hot": "CN",
            "36kr": "CN",
            "cankaoxiaoxi": "CN",
            "zhihu_daily": "CN",
            "ifanr": "CN",
            "techcrunch": "US",
            "the_verge": "US"
        }
        
        # 源类型映射到语言
        source_languages = {
            "zhihu": "zh-CN",
            "baidu": "zh-CN",
            "weibo": "zh-CN",
            "bilibili": "zh-CN",
            "toutiao": "zh-CN",
            "douyin": "zh-CN",
            "hacker_news": "en",
            "bbc_news": "en",
            "bbc_world": "en",
            "bloomberg": "en",
            "bloomberg-markets": "en",
            "bloomberg-tech": "en",
            "bloomberg-china": "zh-CN",
            "v2ex": "zh-CN",
            "github": "en",
            "ithome": "zh-CN",
            "coolapk": "zh-CN",
            "coolapk-app": "zh-CN",
            "coolapk-feed": "zh-CN",
            "cls": "zh-CN",
            "cls-article": "zh-CN",
            "jin10": "zh-CN",
            "xueqiu": "zh-CN",
            "tieba": "zh-CN",
            "kuaishou": "zh-CN",
            "solidot": "zh-CN",
            "zaobao": "zh-CN",
            "thepaper-selenium": "zh-CN",
            "sputniknewscn": "zh-CN",
            "producthunt": "en",
            "linuxdo": "zh-CN",
            "linuxdo-latest": "zh-CN",
            "linuxdo-hot": "zh-CN",
            "kaopu": "zh-CN",
            "gelonghui": "zh-CN",
            "fastbull-express": "zh-CN",
            "fastbull-news": "zh-CN",
            "wallstreetcn": "zh-CN",
            "wallstreetcn-news": "zh-CN",
            "wallstreetcn-hot": "zh-CN",
            "36kr": "zh-CN",
            "cankaoxiaoxi": "zh-CN",
            "zhihu_daily": "zh-CN",
            "ifanr": "zh-CN",
            "techcrunch": "en",
            "the_verge": "en"
        }
        
        # 获取分类映射
        categories_map = {
            "news": 1,      # 新闻资讯
            "tech": 2,      # 科技
            "finance": 3,   # 财经
            "social": 4,    # 社交媒体
            "forum": 5,     # 论坛社区
            "dev": 6,       # 开发者
            "knowledge": 7  # 知识
        }
        logger.info(f"使用分类映射: {categories_map}")
        
        # 如果未获取到源类型，记录警告并返回一个测试源
        if not source_types:
            logger.warning("没有获取到任何源类型，这可能是因为代码中没有可用的新闻源适配器或获取过程出错")
            return [create_test_source("test_source", "测试源 (无可用源)")]
        
        # 直接从硬编码信息创建源对象
        current_time = datetime.utcnow()
        
        for source_type in source_types:
            try:
                # 从映射中获取源信息
                name = source_names.get(source_type, source_type)
                category_str = source_categories.get(source_type, "news")  # 默认使用news分类
                category_id = categories_map.get(category_str, 1)  # 默认使用新闻资讯分类
                country = source_countries.get(source_type, "unknown")
                language = source_languages.get(source_type, "unknown")
                
                # 创建Source模型对象
                source_info = Source(
                    id=source_type,
                    name=name,
                    type=SourceType.WEB,  # 默认使用WEB类型
                    description="",
                    url="",
                    logo="",
                    active=True,
                    priority=0,
                    update_interval=3600,  # 默认1小时
                    cache_ttl=1800,        # 默认30分钟
                    error_count=0,
                    category_id=category_id,
                    country=country,
                    language=language,
                    news_count=0,
                    created_at=current_time,
                    updated_at=current_time,
                    last_updated=None,
                    last_error=None,
                    config={"init": False}
                )
                
                # 添加到源列表
                sources.append(source_info)
                logger.info(f"添加源: {source_type} ({name}), 分类: {category_str}")
                
            except Exception as e:
                logger.error(f"创建源 {source_type} 时出错: {str(e)}")
                logger.error(f"错误详情: {traceback.format_exc()}")
        
        # 按名称排序以保持一致性
        logger.info(f"排序 {len(sources)} 个源...")
        sources.sort(key=lambda x: x.name)
        
        # 添加结果日志
        logger.info(f"将返回 {len(sources)} 个可用源")
        
        # 始终返回sources列表
        return sources
        
    except Exception as e:
        # 捕获整个函数的任何异常
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(f"获取可用源时出现未处理异常: {str(e)}")
        logger.error(f"异常类型: {exc_type}")
        logger.error(f"异常值: {exc_value}")
        logger.error(f"异常详情: {traceback.format_exc()}")
        
        # 返回测试源
        logger.info("返回测试源作为异常情况的备选")
        return [create_test_source("test_source", "测试源 (异常情况)")]


# 辅助函数：创建测试源
def create_test_source(source_id: str, name: str) -> Source:
    """创建一个测试源对象"""
    current_time = datetime.utcnow()
    return Source(
        id=source_id,
        name=name,
        type=SourceType.WEB,
        description="为测试目的创建的源",
        url="",
        logo="",
        active=True,
        priority=0,
        update_interval=3600,
        cache_ttl=1800,
        error_count=0,
        category_id=1,
        country="CN",
        language="zh-CN",
        news_count=0,
        created_at=current_time,
        updated_at=current_time,
        last_updated=None,
        last_error=None,
        config={}
    )


@router.get("/{source_id}", response_model=Source)
async def read_source(
    source_id: str,
    db: Session = Depends(get_db),
):
    """
    Get a specific source by ID.
    """
    source = get_source(db, source_id)
    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )
    
    # Convert timedelta fields to integers
    source_dict = {}
    for key, value in source.__dict__.items():
        if key == "_sa_instance_state":
            continue
            
        # Handle timedelta fields
        if key == "update_interval" and hasattr(value, "total_seconds"):
            source_dict[key] = int(value.total_seconds())
        elif key == "cache_ttl" and hasattr(value, "total_seconds"):
            source_dict[key] = int(value.total_seconds())
        else:
            source_dict[key] = value
            
    # Ensure all required fields have valid values
    if "priority" not in source_dict or source_dict["priority"] is None:
        source_dict["priority"] = 0
    if "error_count" not in source_dict or source_dict["error_count"] is None:
        source_dict["error_count"] = 0
    if "news_count" not in source_dict or source_dict["news_count"] is None:
        source_dict["news_count"] = 0
    
    # Convert dictionary to Pydantic model
    return Source.model_validate(source_dict)


@router.put("/{source_id}", response_model=Source)
async def update_source_api(
    source_id: str,
    source_in: SourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser),
):
    """
    Update a source.
    """
    source = get_source(db, source_id)
    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )
    source = update_source(db, db_obj=source, obj_in=source_in)
    return source


@router.delete("/{source_id}", response_model=bool)
def delete_source_api(
    *,
    db: Session = Depends(get_db),
    source_id: str = Path(..., description="The ID of the source to delete"),
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    删除新闻源
    
    删除指定的新闻源配置，需要超级用户权限
    """
    source = get_source(db=db, id=source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    delete_source(db=db, id=source_id)
    return True


@router.get("/{source_id}/stats", response_model=SourceWithStats)
async def read_source_stats(
    source_id: str,
    db: Session = Depends(get_db),
):
    """
    Get source with news statistics.
    """
    source = crud.get_source_with_stats(db, id=source_id)
    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )

    # Convert the source object to a dictionary
    source_dict = {}
    for key, value in source.__dict__.items():
        if key == "_sa_instance_state":
            continue
            
        # Handle timedelta fields
        if key == "update_interval" and hasattr(value, "total_seconds"):
            source_dict[key] = int(value.total_seconds())
        elif key == "cache_ttl" and hasattr(value, "total_seconds"):
            source_dict[key] = int(value.total_seconds())
        else:
            source_dict[key] = value
    
    # Ensure all required fields have valid values
    if "priority" not in source_dict or source_dict["priority"] is None:
        source_dict["priority"] = 0
    if "error_count" not in source_dict or source_dict["error_count"] is None:
        source_dict["error_count"] = 0
    if "news_count" not in source_dict or source_dict["news_count"] is None:
        source_dict["news_count"] = 0
    
    # Convert dictionary to Pydantic model
    return SourceWithStats.model_validate(source_dict)


@router.post("/aliases", response_model=SourceAlias)
def create_source_alias_api(
    *,
    db: Session = Depends(get_db),
    alias_in: SourceAliasCreate,
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    创建新闻源别名
    
    为新闻源创建一个别名，可用于URL简化，需要超级用户权限
    """
    source = get_source(db=db, id=alias_in.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    alias = create_source_alias(db=db, obj_in=alias_in)
    return alias


@router.delete("/aliases/{alias}", response_model=bool)
def delete_source_alias_api(
    *,
    db: Session = Depends(get_db),
    alias: str = Path(..., description="The alias to delete"),
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    删除新闻源别名
    
    删除指定的新闻源别名，需要超级用户权限
    """
    result = delete_source_alias(db=db, alias=alias)
    if not result:
        raise HTTPException(status_code=404, detail="Alias not found")
    return True 