#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试序列化问题 - 检查ifeng数据源的NewsItemModel对象能否正确序列化为JSON
"""

import os
import sys
import json
import asyncio
import logging
import datetime
import time
from typing import List, Dict, Any, Optional

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("serialize_test")

# 启用调试模式
os.environ["DEBUG"] = "1"

class CustomJSONEncoder(json.JSONEncoder):
    """自定义JSON编码器处理datetime等特殊类型"""
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, datetime.date):
            return obj.isoformat()
        elif hasattr(obj, "__dict__"):
            return obj.__dict__
        return super().default(obj)

async def test_serialization(source_id: str):
    """测试从源获取数据并序列化"""
    try:
        logger.info(f"=== 测试源 {source_id} 的数据序列化 ===")
        
        # 动态导入和创建源
        if source_id == "ifeng-tech":
            from worker.sources.sites.ifeng import IfengTechSource
            source = IfengTechSource()
        elif source_id == "ifeng-studio":
            from worker.sources.sites.ifeng import IfengStudioSource
            source = IfengStudioSource()
        else:
            logger.error(f"未知的源ID: {source_id}")
            return False
        
        # 获取数据
        try:
            logger.info(f"从 {source_id} 获取数据...")
            news_items = await source.fetch()
            logger.info(f"获取到 {len(news_items)} 条新闻")
            
            if not news_items:
                logger.error("没有获取到任何新闻数据")
                return False
            
            # 测试序列化全部数据
            logger.info("测试序列化全部数据...")
            try:
                # 首先尝试标准的json模块进行序列化
                logger.info("使用标准json模块序列化整个列表")
                try:
                    all_items_json = json.dumps(news_items, cls=CustomJSONEncoder)
                    logger.info(f"成功序列化所有数据，长度: {len(all_items_json)}")
                except Exception as e:
                    logger.error(f"整个列表序列化失败: {str(e)}")
                
                # 然后单独测试每条新闻的序列化
                for i, item in enumerate(news_items[:5]):  # 只测试前5条
                    logger.info(f"测试序列化新闻项 {i+1}")
                    
                    # 测试标准json模块
                    try:
                        item_json = json.dumps(item, cls=CustomJSONEncoder)
                        logger.info(f"新闻项 {i+1} 序列化成功，长度: {len(item_json)}")
                    except Exception as e:
                        logger.error(f"新闻项 {i+1} 序列化失败: {str(e)}")
                        
                        # 如果失败，检查每个属性
                        for attr_name in dir(item):
                            if not attr_name.startswith('_') and not callable(getattr(item, attr_name)):
                                try:
                                    attr_value = getattr(item, attr_name)
                                    attr_json = json.dumps({attr_name: attr_value}, cls=CustomJSONEncoder)
                                    logger.info(f"  属性 {attr_name} 序列化成功")
                                except Exception as attr_e:
                                    logger.error(f"  属性 {attr_name} 序列化失败: {str(attr_e)}")
                                    logger.error(f"  属性 {attr_name} 值类型: {type(attr_value)}")
                                    
                                    # 如果是字典，检查键值
                                    if isinstance(attr_value, dict):
                                        for k, v in attr_value.items():
                                            try:
                                                key_json = json.dumps({k: v}, cls=CustomJSONEncoder)
                                                logger.info(f"    键 {k} 序列化成功")
                                            except Exception as key_e:
                                                logger.error(f"    键 {k} 序列化失败: {str(key_e)}")
                                                logger.error(f"    键 {k} 值类型: {type(v)}")
                
                # 现在让我们尝试转换成纯Python字典再序列化
                logger.info("尝试将对象转换为纯Python字典再序列化")
                dicts_list = []
                
                for item in news_items:
                    try:
                        # 手动转换为字典
                        item_dict = {
                            "id": str(item.id),
                            "title": str(item.title),
                            "url": str(item.url),
                            "source_id": str(item.source_id),
                            "source_name": str(item.source_name),
                            "published_at": item.published_at.isoformat() if item.published_at else None,
                            "summary": str(item.summary) if item.summary else "",
                            "content": str(item.content) if item.content else "",
                            "country": str(item.country) if item.country else "",
                            "language": str(item.language) if item.language else "",
                            "category": str(item.category) if item.category else ""
                        }
                        
                        # 对于extra字段，确保每个值都是可序列化的
                        if hasattr(item, "extra") and item.extra:
                            # 深度转换extra字典
                            extra_dict = {}
                            for k, v in item.extra.items():
                                if isinstance(v, (str, int, float, bool, type(None))):
                                    extra_dict[k] = v
                                elif isinstance(v, (datetime.datetime, datetime.date)):
                                    extra_dict[k] = v.isoformat()
                                else:
                                    extra_dict[k] = str(v)
                            item_dict["extra"] = extra_dict
                        else:
                            item_dict["extra"] = {}
                        
                        dicts_list.append(item_dict)
                    except Exception as e:
                        logger.error(f"转换项为字典失败: {str(e)}")
                
                # 序列化转换后的列表
                try:
                    dicts_json = json.dumps(dicts_list)
                    logger.info(f"字典列表序列化成功，长度: {len(dicts_json)}")
                    
                    # 写入文件，以便检查
                    with open(f"{source_id}_serialized.json", "w", encoding="utf-8") as f:
                        f.write(dicts_json)
                    logger.info(f"已将序列化后的数据保存到 {source_id}_serialized.json")
                    
                    # 测试反序列化
                    try:
                        test_parsed = json.loads(dicts_json)
                        logger.info(f"反序列化成功，长度: {len(test_parsed)}")
                    except Exception as e:
                        logger.error(f"反序列化失败: {str(e)}")
                except Exception as e:
                    logger.error(f"字典列表序列化失败: {str(e)}")
                
                # 测试序列化单个项
                if dicts_list:
                    try:
                        single_json = json.dumps(dicts_list[0])
                        logger.info(f"单个字典序列化成功，长度: {len(single_json)}")
                    except Exception as e:
                        logger.error(f"单个字典序列化失败: {str(e)}")
                
                return True
            except Exception as e:
                logger.error(f"序列化测试异常: {str(e)}")
                return False
        except Exception as e:
            logger.error(f"获取数据失败: {str(e)}")
            return False
        finally:
            # 关闭资源
            await source.close()
    except Exception as e:
        logger.error(f"测试过程中出现异常: {str(e)}")
        return False

def test_api_schemas():
    """检查API的响应模型"""
    try:
        logger.info("=== 检查API响应模型 ===")
        
        # 可能的响应模型文件位置
        schema_files = [
            "app/schemas/news.py",
            "app/models/news.py",
            "app/schemas/source.py",
            "app/schemas/__init__.py",
            "app/models/__init__.py"
        ]
        
        for rel_path in schema_files:
            file_path = os.path.join(os.path.dirname(__file__), "..", rel_path)
            if os.path.exists(file_path):
                logger.info(f"找到可能的模型文件: {file_path}")
                
                # 读取文件内容
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # 搜索模型定义
                if "class NewsItem" in content or "class News" in content:
                    logger.info("找到新闻项模型定义")
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if "class NewsItem" in line or "class News" in line:
                            # 显示类定义
                            start = max(0, i-2)
                            end = min(len(lines), i+20)
                            logger.info(f"模型定义 (行 {i+1}):")
                            for j in range(start, end):
                                logger.info(f"{j+1}: {lines[j]}")
                            break
    except Exception as e:
        logger.error(f"检查响应模型时出错: {str(e)}")

def test_alternative_response():
    """
    测试创建和序列化简单的自定义响应
    """
    logger.info("=== 测试简单替代响应 ===")
    
    try:
        # 创建一些测试新闻项
        test_items = [
            {
                "id": "test-id-1",
                "title": "测试标题1",
                "url": "https://example.com/news1",
                "source_id": "test-source",
                "source_name": "测试源",
                "published_at": datetime.datetime.now().isoformat(),
                "summary": "这是一个测试摘要1",
                "content": "这是测试内容1" * 10,
                "extra": {"key1": "value1", "key2": 123}
            },
            {
                "id": "test-id-2",
                "title": "测试标题2",
                "url": "https://example.com/news2",
                "source_id": "test-source",
                "source_name": "测试源",
                "published_at": datetime.datetime.now().isoformat(),
                "summary": "这是一个测试摘要2",
                "content": "这是测试内容2" * 10,
                "extra": {"key1": "value2", "key2": 456}
            }
        ]
        
        # 序列化测试项
        try:
            test_json = json.dumps(test_items)
            logger.info(f"测试项序列化成功，长度: {len(test_json)}")
            
            # 保存到文件
            with open("test_response.json", "w", encoding="utf-8") as f:
                f.write(test_json)
            logger.info("已将测试响应保存到 test_response.json")
            
            # 尝试提供解决方案 - 创建一个简单的API端点示例
            example_code = """
# app/api/endpoints/test.py
from fastapi import APIRouter, Depends
from typing import List, Dict, Any
import json

router = APIRouter()

@router.get("/test/news/{source_id}")
async def test_get_news(source_id: str):
    \"\"\"测试端点 - 返回固定的新闻数据\"\"\"
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

# 在app.main.py中添加此路由器
# app.include_router(test.router, prefix="/api")
"""
            logger.info("建议的解决方案 - 创建测试端点:")
            for i, line in enumerate(example_code.strip().split('\n')):
                logger.info(f"{i+1}: {line}")
            
            # 提供修复ifeng API的建议
            fix_suggestion = """
# 修复sources.py中的端点
@router.get("/external/{source_id}/news", response_model=List[Dict[str, Any]])  # 使用Dict而非NewsItemResponse
async def get_source_news(
    source_id: str,
    force_update: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    news_items = await get_external_news(source_id, force_update)
    
    # 手动转换为字典
    result = []
    for item in news_items:
        try:
            # 转换为纯字典
            item_dict = {
                "id": str(item.id),
                "title": str(item.title),
                "url": str(item.url),
                "source_id": str(item.source_id),
                "source_name": str(item.source_name),
                "published_at": item.published_at.isoformat() if item.published_at else None,
                "summary": str(item.summary) if item.summary else "",
                "content": str(item.content) if item.content else "",
                "country": str(item.country) if item.country else "",
                "language": str(item.language) if item.language else "",
                "category": str(item.category) if item.category else "",
                "extra": {}  # 添加空的extra字典作为默认值
            }
            
            # 安全处理extra属性
            if hasattr(item, "extra") and item.extra:
                for k, v in item.extra.items():
                    if isinstance(v, (str, int, float, bool, type(None))):
                        item_dict["extra"][k] = v
                    elif isinstance(v, (datetime.datetime, datetime.date)):
                        item_dict["extra"][k] = v.isoformat()
                    else:
                        item_dict["extra"][k] = str(v)
            
            result.append(item_dict)
        except Exception as e:
            logger.error(f"转换新闻项时出错: {str(e)}")
    
    return result
"""
            logger.info("建议的API端点修复方案:")
            for i, line in enumerate(fix_suggestion.strip().split('\n')):
                logger.info(f"{i+1}: {line}")
        except Exception as e:
            logger.error(f"测试响应序列化失败: {str(e)}")
    except Exception as e:
        logger.error(f"创建测试响应时出错: {str(e)}")

async def main():
    """主函数"""
    sources = ["ifeng-tech", "ifeng-studio"]
    
    # 测试序列化
    for source_id in sources:
        logger.info("\n" + "="*80)
        logger.info(f"测试源 {source_id} 的数据序列化")
        logger.info("="*80)
        
        # 测试序列化
        await test_serialization(source_id)
    
    # 检查API响应模型
    test_api_schemas()
    
    # 测试替代响应
    test_alternative_response()
    
    logger.info("\n" + "="*30 + " 测试完成 " + "="*30)

if __name__ == "__main__":
    asyncio.run(main()) 