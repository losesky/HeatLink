import asyncio
import aiohttp
import json
import random
import time
from bs4 import BeautifulSoup
import re
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 财联社URL
CLS_BASE_URL = "https://www.cls.cn"
CLS_TELEGRAPH_URL = "https://www.cls.cn/telegraph"
CLS_GLOBAL_MARKET_URL = "https://www.cls.cn/subject/1556"  # 环球市场情报
CLS_HOT_ARTICLE_URL = "https://www.cls.cn/telegraph?type=hot"  # 热门文章

# 可能的API端点
API_ENDPOINTS = [
    # 原有API
    "https://www.cls.cn/nodeapi/telegraphs",
    "https://www.cls.cn/nodeapi/telegraphList",
    # 可能的新API
    "https://www.cls.cn/v1/telegraphs",
    "https://www.cls.cn/api/v1/roll/get-list",
    "https://www.cls.cn/api/v1/telegraph/get-list",
    "https://www.cls.cn/api/v1/roll/get-page-data"
]

# 用户代理
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0"
]


async def check_api(url, params=None):
    """检查API端点是否可用并返回响应内容"""
    try:
        # 基本HTTP头
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.cls.cn/",
            "Content-Type": "application/json",
            "x-app-id": "CailianpressWeb",
            "x-os": "web",
            "x-sv": "9.1.0",
            "Origin": "https://www.cls.cn"
        }

        if params is None:
            # 默认参数
            params = {
                "app": "CailianpressWeb",
                "os": "web",
                "sv": "9.1.0",
                "category": "",
                "rn": 20,
                "lastTime": int(time.time() * 1000),
                "last_time": int(time.time() * 1000),
                "subscribe": 0
            }

        logger.info(f"正在检查API: {url}")
        logger.info(f"请求参数: {params}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=10) as response:
                status = response.status
                logger.info(f"API响应状态码: {status}")
                
                try:
                    data = await response.json()
                    logger.info(f"API响应为JSON格式")
                    
                    # 保存响应到文件
                    filename = f"cls_api_response_{url.split('/')[-1]}_{int(time.time())}.json"
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    logger.info(f"响应已保存到: {filename}")
                    
                    return {
                        "success": True,
                        "status": status,
                        "data": data,
                        "filename": filename
                    }
                except:
                    # 如果不是JSON，尝试获取文本内容
                    text = await response.text()
                    logger.info(f"API响应不是JSON格式，获取到文本内容，长度: {len(text)}")
                    
                    # 保存响应到文件
                    filename = f"cls_api_response_{url.split('/')[-1]}_{int(time.time())}.txt"
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(text)
                    logger.info(f"响应已保存到: {filename}")
                    
                    return {
                        "success": False,
                        "status": status,
                        "text": text[:500] + "..." if len(text) > 500 else text,
                        "filename": filename
                    }
    except Exception as e:
        logger.error(f"检查API时出错: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


async def check_webpage(url):
    """检查网页结构并尝试提取数据"""
    try:
        # 基本HTTP头
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.cls.cn/",
            "Cache-Control": "max-age=0",
            "Upgrade-Insecure-Requests": "1"
        }

        logger.info(f"正在检查网页: {url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                status = response.status
                logger.info(f"网页响应状态码: {status}")
                
                html = await response.text()
                logger.info(f"获取到HTML内容，长度: {len(html)}")
                
                # 保存HTML到文件
                filename = f"cls_webpage_{url.split('/')[-1].split('?')[0]}_{int(time.time())}.html"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(html)
                logger.info(f"HTML已保存到: {filename}")
                
                # 使用BeautifulSoup解析HTML
                soup = BeautifulSoup(html, 'html.parser')
                
                # 尝试查找可能的数据
                articles = []
                # 1. 查找文章列表
                article_elements = soup.select(".telegraph-item, .roll-item, .hot-item, .article-item, .cls-list-item")
                if article_elements:
                    logger.info(f"找到 {len(article_elements)} 个可能的文章元素")
                
                # 2. 尝试从script标签中提取数据
                data_from_script = None
                for script in soup.find_all('script'):
                    script_text = script.string
                    if not script_text:
                        continue
                    
                    # 查找可能包含数据的JSON
                    json_patterns = [
                        r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
                        r'window\.__REDUX_STATE__\s*=\s*({.*?});',
                        r'__REDUX_STATE__\s*=\s*({.*?});',
                        r'telegraph_list":\s*(\[.*?\])',
                        r'REDUX_STATE\s*=\s*({.*?});\s*</script>'
                    ]
                    
                    for pattern in json_patterns:
                        try:
                            match = re.search(pattern, script_text, re.DOTALL)
                            if match:
                                data_from_script = match.group(1)
                                logger.info(f"从脚本中找到可能的数据")
                                # 保存到文件
                                script_filename = f"cls_script_data_{int(time.time())}.json"
                                with open(script_filename, 'w', encoding='utf-8') as f:
                                    f.write(data_from_script)
                                logger.info(f"脚本数据已保存到: {script_filename}")
                                break
                        except Exception as e:
                            logger.warning(f"解析脚本数据时出错: {str(e)}")
                
                return {
                    "success": True,
                    "status": status,
                    "html_file": filename,
                    "article_count": len(article_elements),
                    "has_script_data": data_from_script is not None
                }
    except Exception as e:
        logger.error(f"检查网页时出错: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


async def main():
    """主函数"""
    logger.info("开始测试财联社API和网页")
    
    # 1. 检查所有可能的API端点
    logger.info("=== 测试所有可能的API端点 ===")
    for endpoint in API_ENDPOINTS:
        result = await check_api(endpoint)
        logger.info(f"API {endpoint} 测试结果: {'成功' if result.get('success') else '失败'}")
        logger.info("-" * 80)
    
    # 2. 测试网页
    logger.info("=== 测试网页结构 ===")
    webpages = [CLS_TELEGRAPH_URL, CLS_HOT_ARTICLE_URL, CLS_GLOBAL_MARKET_URL]
    for webpage in webpages:
        result = await check_webpage(webpage)
        logger.info(f"网页 {webpage} 测试结果: {'成功' if result.get('success') else '失败'}")
        logger.info("-" * 80)
    
    logger.info("测试完成！请查看生成的文件以获取更多信息。")


if __name__ == "__main__":
    asyncio.run(main()) 