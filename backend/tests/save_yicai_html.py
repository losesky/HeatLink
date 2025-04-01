#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
工具脚本：保存第一财经新闻页面HTML到文件
用于后续测试和分析
"""

import sys
import os
import logging
import random
import asyncio
import time
import argparse
from pathlib import Path
from datetime import datetime

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("save_yicai_html")

# 添加项目根目录到Python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

try:
    # 尝试导入aiohttp和BeautifulSoup
    import aiohttp
    from bs4 import BeautifulSoup
except ImportError as e:
    logger.error(f"缺少必要的依赖: {e}")
    logger.info("请安装必要的依赖: pip install aiohttp beautifulsoup4")
    sys.exit(1)

# 配置
URL = "https://www.yicai.com/news/"
OUTPUT_DIR = Path(__file__).resolve().parent / "html_data"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/123.0"
]

async def fetch_html(url: str) -> str:
    """获取页面HTML内容"""
    logger.info(f"正在获取页面: {url}")
    
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
        "Upgrade-Insecure-Requests": "1",
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status != 200:
                    logger.error(f"获取页面失败，状态码: {response.status}")
                    return ""
                
                html = await response.text()
                logger.info(f"成功获取页面，长度: {len(html)} 字节")
                return html
    except Exception as e:
        logger.error(f"获取页面时发生错误: {e}")
        return ""

def save_html(html: str, output_path: Path) -> bool:
    """保存HTML内容到文件"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        logger.info(f"成功保存HTML到文件: {output_path}")
        return True
    except Exception as e:
        logger.error(f"保存HTML到文件时发生错误: {e}")
        return False

def extract_news_count(html: str) -> int:
    """从HTML中提取新闻数量"""
    if not html:
        return 0
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        news_container = soup.select_one("#newslist")
        if not news_container:
            return 0
        
        news_items = news_container.select("a.f-db")
        return len(news_items)
    except Exception as e:
        logger.error(f"提取新闻数量时发生错误: {e}")
        return 0

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="保存第一财经新闻页面HTML")
    parser.add_argument("--url", default=URL, help=f"要获取的URL (默认: {URL})")
    parser.add_argument("--output", help="输出文件路径 (默认自动生成)")
    parser.add_argument("--retry", type=int, default=3, help="重试次数 (默认: 3)")
    args = parser.parse_args()
    
    # 创建输出目录
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    
    # 确定输出文件路径
    output_path = args.output
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"yicai_news_{timestamp}.html"
    else:
        output_path = Path(output_path)
    
    # 获取页面内容
    html = ""
    retry_count = 0
    
    while not html and retry_count < args.retry:
        html = await fetch_html(args.url)
        if not html:
            retry_count += 1
            if retry_count < args.retry:
                logger.warning(f"获取失败，将在3秒后重试 ({retry_count}/{args.retry})...")
                await asyncio.sleep(3)
    
    if not html:
        logger.error(f"在 {args.retry} 次尝试后仍然无法获取页面内容")
        return False
    
    # 提取新闻数量
    news_count = extract_news_count(html)
    logger.info(f"从页面中提取到 {news_count} 条新闻")
    
    # 如果新闻数量为0，可能是页面结构有问题
    if news_count == 0:
        logger.warning("未从页面中提取到任何新闻，可能页面结构有变化或加载不完整")
        
        # 保存到错误文件
        error_output_path = OUTPUT_DIR / f"error_{output_path.name}"
        save_html(html, error_output_path)
        logger.info(f"已将原始HTML保存到错误文件: {error_output_path}")
        
        # 是否仍然保存
        response = input("是否仍然保存HTML到目标文件? (y/N): ")
        if response.lower() != 'y':
            logger.info("操作已取消")
            return False
    
    # 保存HTML到文件
    return save_html(html, output_path)

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 