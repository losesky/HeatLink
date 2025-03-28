from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from worker.sources.provider import DefaultNewsSourceProvider

router = APIRouter()

class TestSourceRequest(BaseModel):
    source_id: str
    force_update: bool = False

@router.post("/test_source", response_model=List[Dict[str, Any]])
async def test_source(
    request: TestSourceRequest
):
    """
    测试新闻源适配器
    直接使用DefaultNewsSourceProvider获取新闻，绕过API层的源提供者
    确保使用最新的数据库配置
    """
    # 创建源提供者 - 重新初始化以确保使用最新的数据库配置
    source_provider = DefaultNewsSourceProvider()
    
    # 获取新闻源
    source = source_provider.get_source(request.source_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"新闻源 {request.source_id} 不存在")
    
    try:
        # 输出源配置信息（调试用）
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"测试源 {request.source_id} 的配置: {source.config}")
        
        # 如果是CLS源，特别记录其Selenium配置
        if request.source_id.startswith('cls'):
            logger.info(f"CLS源配置详情:")
            logger.info(f"- use_selenium: {getattr(source, 'use_selenium', None)}")
            logger.info(f"- use_direct_api: {getattr(source, 'use_direct_api', None)}")
            logger.info(f"- use_scraping: {getattr(source, 'use_scraping', None)}")
            logger.info(f"- use_backup_api: {getattr(source, 'use_backup_api', None)}")
        
        # 获取新闻
        news_items = await source.get_news(force_update=request.force_update)
        
        # 格式化返回数据
        result = []
        for item in news_items:
            # 检查是否是模拟数据
            is_mock = item.extra.get("is_mock", False) if item.extra else False
            
            news_dict = item.to_dict()
            # 添加标记，表示这是通过测试端点获取的
            news_dict["_test_info"] = {
                "is_mock": is_mock,
                "from_test_endpoint": True
            }
            
            result.append(news_dict)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 