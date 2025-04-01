#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试API响应问题 - 专门检查为什么API返回空数组
"""

import os
import sys
import json
import time
import logging
import requests
from urllib.parse import urljoin

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("api_test")

# API基础URL
BASE_URL = "http://127.0.0.1:8000"

def test_api_with_different_methods(source_id, force_update=True):
    """
    使用不同的HTTP客户端和方法测试API
    """
    logger.info(f"=== 测试源 {source_id} 的API响应 ===")
    
    # 构建API URL
    api_url = f"{BASE_URL}/api/sources/external/{source_id}/news"
    params = {"force_update": "true" if force_update else "false"}
    
    # 1. 使用requests库测试
    logger.info("方法1: 使用requests库")
    try:
        response = requests.get(api_url, params=params)
        logger.info(f"状态码: {response.status_code}")
        logger.info(f"响应头: {dict(response.headers)}")
        logger.info(f"响应内容类型: {response.headers.get('Content-Type', 'unknown')}")
        logger.info(f"响应内容长度: {len(response.text)}")
        logger.info(f"响应内容前100个字符: {response.text[:100]}")
        
        # 尝试解析JSON
        try:
            data = response.json()
            logger.info(f"解析的JSON类型: {type(data)}")
            logger.info(f"解析的JSON长度: {len(data) if isinstance(data, list) else '非列表'}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {str(e)}")
    except Exception as e:
        logger.error(f"请求失败: {str(e)}")
    
    # 2. 使用curl命令测试
    logger.info("\n方法2: 使用os.system执行curl命令")
    try:
        curl_cmd = f'curl -v "{api_url}?force_update={str(force_update).lower()}" -H "Accept: application/json"'
        logger.info(f"执行命令: {curl_cmd}")
        os.system(curl_cmd + " > curl_output.txt 2>&1")
        
        # 读取curl输出
        with open("curl_output.txt", "r") as f:
            curl_output = f.read()
        
        logger.info(f"curl输出长度: {len(curl_output)}")
        # 显示关键部分
        for line in curl_output.split('\n'):
            if "< HTTP/" in line or "< Content-Type:" in line or "< Content-Length:" in line:
                logger.info(f"curl响应头: {line.strip()}")
    except Exception as e:
        logger.error(f"curl测试失败: {str(e)}")
    
    # 3. 使用requests但带不同的headers
    logger.info("\n方法3: 使用requests库但带完整headers")
    try:
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        }
        
        response = requests.get(api_url, params=params, headers=headers)
        logger.info(f"状态码: {response.status_code}")
        logger.info(f"响应头: {dict(response.headers)}")
        logger.info(f"响应内容类型: {response.headers.get('Content-Type', 'unknown')}")
        logger.info(f"响应内容长度: {len(response.text)}")
        logger.info(f"响应内容前100个字符: {response.text[:100]}")
        
        # 尝试解析JSON
        try:
            data = response.json()
            logger.info(f"解析的JSON类型: {type(data)}")
            logger.info(f"解析的JSON长度: {len(data) if isinstance(data, list) else '非列表'}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {str(e)}")
    except Exception as e:
        logger.error(f"请求失败: {str(e)}")
    
    # 4. 检查其他API端点是否正常工作
    logger.info("\n方法4: 测试其他API端点")
    try:
        # 测试API文档端点
        docs_url = f"{BASE_URL}/api/docs"
        response = requests.get(docs_url)
        logger.info(f"API文档状态码: {response.status_code}")
        logger.info(f"API文档响应长度: {len(response.text)}")
        
        # 测试监控源端点
        monitor_url = f"{BASE_URL}/api/monitor/sources"
        response = requests.get(monitor_url)
        logger.info(f"监控源状态码: {response.status_code}")
        
        # 尝试解析监控源响应
        try:
            data = response.json()
            logger.info(f"监控源响应类型: {type(data)}")
            logger.info(f"监控源响应长度: {len(data) if isinstance(data, list) else '非列表'}")
            
            # 检查监控源响应中是否有我们测试的源
            source_found = False
            for item in data:
                if isinstance(item, dict) and item.get("source_id") == source_id:
                    source_found = True
                    logger.info(f"在监控源中找到源 {source_id}: {item}")
                    break
            
            if not source_found:
                logger.warning(f"在监控源响应中未找到源 {source_id}")
        except json.JSONDecodeError as e:
            logger.error(f"监控源JSON解析失败: {str(e)}")
    except Exception as e:
        logger.error(f"其他API端点测试失败: {str(e)}")

def check_api_endpoint_implementation():
    """
    检查API端点实现代码
    """
    logger.info("=== 检查API端点实现 ===")
    
    # 假设标准的FastAPI后端文件布局
    possible_paths = [
        "app/api/endpoints/sources.py",
        "app/routers/sources.py",
        "app/api/routes/sources.py",
        "app/api/v1/endpoints/sources.py"
    ]
    
    for rel_path in possible_paths:
        file_path = os.path.join(os.path.dirname(__file__), "..", rel_path)
        if os.path.exists(file_path):
            logger.info(f"找到API端点文件: {file_path}")
            
            # 读取文件内容
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 搜索外部源API端点的代码
            if "external/{source_id}/news" in content or "external/{source_id}" in content:
                logger.info("找到外部源API端点定义")
                
                # 显示代码片段
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if "external/{source_id}/news" in line or "external/{source_id}" in line:
                        # 显示周围的代码
                        start = max(0, i-10)
                        end = min(len(lines), i+30)
                        logger.info(f"API端点定义 (行 {i+1}):")
                        for j in range(start, end):
                            logger.info(f"{j+1}: {lines[j]}")
                        break
                
                # 检查一些典型问题
                if "response_model" in content and ("List[" in content or "List " in content):
                    logger.info("API使用了List响应模型")
                    
                    # 检查响应模型导入
                    for line in lines:
                        if "from typing import List" in line:
                            logger.info(f"找到List导入: {line}")
                        elif "response_model=" in line and "List" in line:
                            logger.info(f"找到响应模型定义: {line}")
                
                # 检查权限或认证要求
                if "Depends(get_current_user)" in content or "Depends(get_current_active_user)" in content:
                    logger.warning("API端点需要用户认证")
                
                # 检查数据转换
                for line in lines:
                    if "return" in line and "news" in line.lower():
                        logger.info(f"找到返回语句: {line}")
            else:
                logger.warning("未在文件中找到外部源API端点定义")
    
    # 搜索API异常处理代码
    exception_handlers_paths = [
        "app/api/deps.py",
        "app/dependencies.py",
        "app/core/error_handlers.py",
        "app/middleware.py"
    ]
    
    for rel_path in exception_handlers_paths:
        file_path = os.path.join(os.path.dirname(__file__), "..", rel_path)
        if os.path.exists(file_path):
            logger.info(f"找到可能的异常处理文件: {file_path}")
            
            # 读取文件内容
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 搜索异常处理代码
            if "except" in content and "return" in content:
                logger.info("找到异常处理代码")
                
                # 显示代码片段
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if "except" in line and "Exception" in line:
                        # 显示周围的代码
                        start = max(0, i-5)
                        end = min(len(lines), i+15)
                        logger.info(f"异常处理代码 (行 {i+1}):")
                        for j in range(start, end):
                            logger.info(f"{j+1}: {lines[j]}")

def main():
    """主函数"""
    sources = ["ifeng-tech", "ifeng-studio"]
    
    for source_id in sources:
        logger.info("\n" + "="*80)
        logger.info(f"测试数据源 {source_id} 的API响应")
        logger.info("="*80)
        
        # 使用不同的方法测试API
        test_api_with_different_methods(source_id, force_update=True)
    
    # 检查API端点实现
    check_api_endpoint_implementation()
    
    logger.info("\n" + "="*30 + " 测试完成 " + "="*30)

if __name__ == "__main__":
    main() 