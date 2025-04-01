from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import json
import datetime

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

@router.get("/news/{source_id}")
async def test_get_news(source_id: str):
    """测试端点 - 返回固定的新闻数据"""
    # 创建一些测试新闻项
    test_items = [
        {
            "id": "test-id-1",
            "title": "测试标题1",
            "url": "https://example.com/news1",
            "source_id": source_id,
            "source_name": "测试源",
            "published_at": "2025-03-31T12:00:00",
            "summary": "这是一个测试摘要1",
            "content": "这是测试内容1" * 10,
            "extra": {"key1": "value1", "key2": 123}
        },
        {
            "id": "test-id-2",
            "title": "测试标题2",
            "url": "https://example.com/news2",
            "source_id": source_id,
            "source_name": "测试源",
            "published_at": "2025-03-31T13:00:00",
            "summary": "这是一个测试摘要2",
            "content": "这是测试内容2" * 10,
            "extra": {"key1": "value2", "key2": 456}
        }
    ]
    return test_items 