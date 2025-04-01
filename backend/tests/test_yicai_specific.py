#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试脚本：专门测试第一财经新闻页面HTML结构解析
测试网页：https://www.yicai.com/news/
"""

import sys
import os
import asyncio
import logging
import datetime
import hashlib
import re
from pathlib import Path
from typing import List, Dict, Any

# 添加项目根目录到Python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

# 导入相关模块
from worker.sources.base import NewsItemModel
from bs4 import BeautifulSoup
import aiohttp

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_yicai_specific")

# 测试配置
TEST_URL = "https://www.yicai.com/news/"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
]

async def fetch_html(url: str) -> str:
    """获取页面HTML内容"""
    logger.info(f"正在获取页面: {url}")
    
    headers = {
        "User-Agent": USER_AGENTS[0],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
        "Upgrade-Insecure-Requests": "1",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=30) as response:
            if response.status != 200:
                logger.error(f"获取页面失败，状态码: {response.status}")
                return ""
            
            html = await response.text()
            logger.info(f"成功获取页面，长度: {len(html)} 字节")
            return html

def parse_news_items(html: str) -> List[NewsItemModel]:
    """解析新闻列表页面，提取新闻项"""
    if not html:
        logger.error("HTML内容为空，无法解析")
        return []
    
    logger.info("开始解析HTML内容...")
    soup = BeautifulSoup(html, 'html.parser')
    
    # 定位新闻列表容器
    news_container = soup.select_one("#newslist")
    if not news_container:
        logger.error("未找到新闻列表容器 #newslist")
        return []
    
    # 查找所有新闻项
    news_items_html = news_container.select("a.f-db")
    logger.info(f"找到 {len(news_items_html)} 条新闻")
    
    news_items = []
    for index, item_html in enumerate(news_items_html):
        try:
            # 提取新闻项基本信息
            href = item_html.get("href", "")
            url = f"https://www.yicai.com{href}" if href.startswith("/") else href
            
            # 提取标题
            title_elem = item_html.select_one("h2")
            title = title_elem.text.strip() if title_elem else ""
            
            # 提取摘要
            summary_elem = item_html.select_one("p")
            summary = summary_elem.text.strip() if summary_elem else ""
            
            # 提取时间
            time_elem = item_html.select_one(".rightspan span:last-child")
            time_text = time_elem.text.strip() if time_elem else ""
            
            # 提取图片URL
            img_elem = item_html.select_one("img.u-img")
            image_url = img_elem.get("src", "") if img_elem else ""
            
            # 解析时间文本，转换为datetime对象
            published_at = datetime.datetime.now()
            if time_text:
                try:
                    # 处理"5分钟前"，"1小时前"等格式
                    if "分钟前" in time_text:
                        minutes = int(time_text.replace("分钟前", "").strip())
                        published_at = datetime.datetime.now() - datetime.timedelta(minutes=minutes)
                    elif "小时前" in time_text:
                        hours = int(time_text.replace("小时前", "").strip())
                        published_at = datetime.datetime.now() - datetime.timedelta(hours=hours)
                    elif "天前" in time_text:
                        days = int(time_text.replace("天前", "").strip())
                        published_at = datetime.datetime.now() - datetime.timedelta(days=days)
                except Exception as e:
                    logger.warning(f"解析时间失败: {time_text}, 错误: {str(e)}")
            
            # 生成唯一ID
            news_id = hashlib.md5(f"yicai-news-{title}-{url}".encode()).hexdigest()
            
            # 创建新闻项对象
            if title and url:
                news_item = NewsItemModel(
                    id=news_id,
                    title=title,
                    url=url,
                    source_id="yicai",
                    source_name="第一财经",
                    content="",
                    summary=summary,
                    image_url=image_url,
                    published_at=published_at,
                    country="CN",
                    language="zh-CN",
                    extra={
                        "time_text": time_text,
                        "type": "news",
                        "rank": index + 1,
                        "source_from": "html_parsing_test"
                    }
                )
                news_items.append(news_item)
        except Exception as e:
            logger.error(f"解析新闻项 {index} 时出错: {str(e)}")
    
    logger.info(f"成功解析 {len(news_items)} 条新闻")
    return news_items

async def test_parsing():
    """测试HTML解析功能"""
    try:
        # 获取页面HTML
        html = await fetch_html(TEST_URL)
        
        if not html:
            logger.error("获取页面HTML失败，测试终止")
            return
        
        # 解析新闻项
        news_items = parse_news_items(html)
        
        if not news_items:
            logger.warning("未解析到任何新闻项")
            return
        
        # 显示新闻项详情
        logger.info("\n解析结果预览:")
        for i, item in enumerate(news_items[:5]):  # 只显示前5条
            logger.info(f"新闻 {i+1}:")
            logger.info(f"  标题: {item.title}")
            logger.info(f"  链接: {item.url}")
            logger.info(f"  发布时间: {item.published_at}")
            logger.info(f"  时间文本: {item.extra.get('time_text', '')}")
            if item.summary:
                logger.info(f"  摘要: {item.summary[:100]}..." if len(item.summary) > 100 else f"  摘要: {item.summary}")
            if item.image_url:
                logger.info(f"  图片URL: {item.image_url}")
            logger.info("")
        
        # 分析解析结果
        if len(news_items) > 0:
            logger.info("解析成功率分析:")
            titles_count = sum(1 for item in news_items if item.title)
            urls_count = sum(1 for item in news_items if item.url)
            summaries_count = sum(1 for item in news_items if item.summary)
            images_count = sum(1 for item in news_items if item.image_url)
            
            logger.info(f"  标题成功率: {titles_count}/{len(news_items)} ({titles_count/len(news_items)*100:.1f}%)")
            logger.info(f"  链接成功率: {urls_count}/{len(news_items)} ({urls_count/len(news_items)*100:.1f}%)")
            logger.info(f"  摘要成功率: {summaries_count}/{len(news_items)} ({summaries_count/len(news_items)*100:.1f}%)")
            logger.info(f"  图片成功率: {images_count}/{len(news_items)} ({images_count/len(news_items)*100:.1f}%)")
        
        logger.info("测试完成！")
        
    except Exception as e:
        logger.error(f"测试过程中发生错误: {str(e)}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_parsing()) 