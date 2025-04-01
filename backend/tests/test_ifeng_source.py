#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试凤凰网数据源直接获取及API响应比较，诊断空返回问题
"""

import os
import sys
import json
import asyncio
import logging
import datetime
import time
import requests
from typing import List, Dict, Any, Optional

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ifeng_test")

# 设置调试模式
os.environ["DEBUG"] = "1"

async def test_direct_source(source_id: str):
    """
    直接从数据源获取数据
    """
    try:
        logger.info(f"=== 开始直接测试数据源: {source_id} ===")
        
        # 动态导入
        if source_id == "ifeng-tech":
            from worker.sources.sites.ifeng import IfengTechSource
            source = IfengTechSource()
        elif source_id == "ifeng-studio":
            from worker.sources.sites.ifeng import IfengStudioSource
            source = IfengStudioSource()
        else:
            logger.error(f"未知的数据源ID: {source_id}")
            return
        
        # 获取数据
        start_time = time.time()
        news_items = await source.fetch()
        elapsed = time.time() - start_time
        
        logger.info(f"直接获取耗时: {elapsed:.2f}秒")
        logger.info(f"直接获取到 {len(news_items)} 条新闻")
        
        # 打印获取到的前几条新闻
        if news_items:
            logger.info("=== 前3条新闻详情 ===")
            for i, item in enumerate(news_items[:3]):
                logger.info(f"新闻{i+1}: {item.title}")
                logger.info(f"  URL: {item.url}")
                logger.info(f"  发布时间: {item.published_at}")
                logger.info(f"  ID: {item.id}")
                
                # 检查关键属性是否可序列化
                try:
                    # 测试序列化
                    item_dict = {
                        "id": item.id,
                        "title": item.title,
                        "url": item.url,
                        "source_id": item.source_id,
                        "source_name": item.source_name,
                        "published_at": item.published_at.isoformat() if item.published_at else None,
                        "summary": item.summary,
                        "content": item.content
                    }
                    json_str = json.dumps(item_dict, ensure_ascii=False)
                    logger.info(f"  序列化成功: 长度={len(json_str)}")
                except Exception as e:
                    logger.error(f"  序列化失败: {str(e)}")
                    
                    # 详细检查每个字段
                    for field, value in item_dict.items():
                        try:
                            json.dumps({field: value}, ensure_ascii=False)
                        except Exception as e:
                            logger.error(f"  字段 {field} 序列化失败: {str(e)}, 值类型: {type(value)}")
        else:
            logger.warning("直接获取未获得任何新闻数据!")
        
        # 清理资源
        await source.close()
        
        return news_items
    except Exception as e:
        logger.error(f"直接测试源时出错: {str(e)}", exc_info=True)
        return []

def test_api_endpoint(source_id: str, force_update: bool = True):
    """
    测试从API获取数据
    """
    try:
        logger.info(f"=== 开始测试API: {source_id} ===")
        
        # 准备请求
        url = f"http://127.0.0.1:8000/api/sources/external/{source_id}/news"
        params = {"force_update": "true" if force_update else "false"}
        headers = {"Accept": "application/json"}
        
        logger.info(f"请求URL: {url}")
        logger.info(f"参数: {params}")
        
        # 发送请求
        start_time = time.time()
        response = requests.get(url, params=params, headers=headers)
        elapsed = time.time() - start_time
        
        logger.info(f"API请求耗时: {elapsed:.2f}秒")
        logger.info(f"状态码: {response.status_code}")
        logger.info(f"响应头: {dict(response.headers)}")
        
        # 检查响应
        try:
            if response.status_code == 200:
                # 尝试解析JSON
                try:
                    data = response.json()
                    logger.info(f"响应数据类型: {type(data)}")
                    logger.info(f"响应数据长度: {len(data) if isinstance(data, list) else '非列表'}")
                    
                    # 显示原始响应内容
                    content = response.text
                    logger.info(f"原始响应内容 (前100字符): {content[:100]}")
                    logger.info(f"响应内容长度: {len(content)}")
                    
                    # 检查响应是否为空数组
                    if content.strip() == "[]":
                        logger.warning("API返回了空数组 []")
                    
                    return data
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析失败: {str(e)}")
                    logger.info(f"响应内容: {response.text}")
            else:
                logger.error(f"API请求失败，状态码: {response.status_code}")
                logger.info(f"响应内容: {response.text}")
        except Exception as e:
            logger.error(f"处理API响应时出错: {str(e)}")
        
        return None
    except Exception as e:
        logger.error(f"测试API时出错: {str(e)}", exc_info=True)
        return None

def test_with_source_provider(source_id: str):
    """
    使用SourceProvider进行测试
    """
    try:
        logger.info(f"=== 使用SourceProvider测试: {source_id} ===")
        from worker.sources.provider import SourceProvider
        
        # 创建异步运行环境
        async def test_provider():
            provider = SourceProvider()
            
            # 获取源
            source = await provider.get_source(source_id)
            if not source:
                logger.error(f"SourceProvider无法获取源: {source_id}")
                return []
            
            logger.info(f"成功获取源: {source.name} (类型: {type(source).__name__})")
            
            # 获取数据
            start_time = time.time()
            news_items = await source.fetch()
            elapsed = time.time() - start_time
            
            logger.info(f"获取耗时: {elapsed:.2f}秒")
            logger.info(f"获取到 {len(news_items)} 条新闻")
            
            # 打印获取到的前几条新闻
            if news_items:
                logger.info("=== 前3条新闻详情 ===")
                for i, item in enumerate(news_items[:3]):
                    logger.info(f"新闻{i+1}: {item.title}")
                    logger.info(f"  URL: {item.url}")
                    logger.info(f"  发布时间: {item.published_at}")
            else:
                logger.warning("未获得任何新闻数据!")
            
            return news_items
        
        # 运行测试
        return asyncio.run(test_provider())
    except Exception as e:
        logger.error(f"使用SourceProvider测试时出错: {str(e)}", exc_info=True)
        return []

def examine_backend_code():
    """
    检查后端API代码，寻找可能的问题点
    """
    try:
        logger.info("=== 检查后端API代码 ===")
        
        # 尝试查找和分析相关API端点实现
        import glob
        
        # 查找可能的API端点实现文件
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        api_files = []
        
        # 查找可能包含API端点的文件
        for pattern in ["**/api/**/*.py", "**/endpoints/**/*.py", "**/routes/**/*.py"]:
            matches = glob.glob(os.path.join(backend_dir, pattern), recursive=True)
            api_files.extend(matches)
        
        logger.info(f"找到 {len(api_files)} 个可能包含API定义的文件")
        
        # 检查这些文件中是否有external/{source_id}/news相关端点
        found = False
        for file_path in api_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if "sources/external" in content or "external/{source_id}/news" in content:
                    logger.info(f"找到可能的API实现: {file_path}")
                    found = True
                    
                    # 显示文件内容的相关部分
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if "sources/external" in line or "external/{source_id}/news" in line:
                            # 显示周围的代码
                            start = max(0, i-10)
                            end = min(len(lines), i+20)
                            logger.info(f"相关代码片段 ({file_path}, 行 {i+1}):")
                            for j in range(start, end):
                                logger.info(f"{j+1}: {lines[j]}")
                            break
        
        if not found:
            logger.warning("未找到包含外部源API端点的代码文件")
    except Exception as e:
        logger.error(f"检查后端代码时出错: {str(e)}", exc_info=True)

async def main():
    """主函数"""
    # 测试的数据源
    sources = ["ifeng-tech", "ifeng-studio"]
    
    for source_id in sources:
        logger.info("\n" + "="*80)
        logger.info(f"开始测试数据源: {source_id}")
        logger.info("="*80)
        
        # 1. 直接从数据源获取
        direct_items = await test_direct_source(source_id)
        
        # 2. 通过API获取
        api_items = test_api_endpoint(source_id, force_update=True)
        
        # 3. 通过SourceProvider获取
        provider_items = test_with_source_provider(source_id)
        
        # 结果对比
        logger.info("\n" + "="*30 + " 结果对比 " + "="*30)
        logger.info(f"直接从数据源获取: {len(direct_items) if direct_items else 0} 条")
        logger.info(f"通过API获取: {len(api_items) if api_items else 0} 条")
        logger.info(f"通过SourceProvider获取: {len(provider_items) if provider_items else 0} 条")
        
        # 如果API返回为空但直接获取有数据，进一步分析
        if (not api_items or len(api_items) == 0) and direct_items and len(direct_items) > 0:
            logger.warning("检测到API返回空但直接获取有数据的情况，将进一步分析")
            examine_backend_code()
    
    logger.info("\n" + "="*30 + " 测试完成 " + "="*30)

if __name__ == "__main__":
    asyncio.run(main()) 