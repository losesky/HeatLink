#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试脚本：直接从HTML分析第一财经新闻页面内容
使用BeautifulSoup提取页面内容，无需Selenium
"""

import sys
import os
import logging
import datetime
import hashlib
import re
import json
from pathlib import Path
from typing import List, Dict, Any

# 添加项目根目录到Python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

# 导入相关模块
from worker.sources.base import NewsItemModel
from bs4 import BeautifulSoup

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_yicai_html")

def parse_yicai_html(html_content: str) -> List[Dict[str, Any]]:
    """
    从提供的HTML内容中解析第一财经新闻
    
    Args:
        html_content: HTML页面内容
        
    Returns:
        提取的新闻项列表
    """
    logger.info("开始解析HTML内容...")
    
    if not html_content:
        logger.error("HTML内容为空")
        return []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 查找新闻列表容器
    news_container = soup.select_one("#newslist")
    if not news_container:
        logger.error("未找到新闻列表容器 #newslist")
        return []
    
    # 查找所有新闻项元素
    news_items = news_container.select("a.f-db")
    logger.info(f"找到 {len(news_items)} 条新闻")
    
    result = []
    for index, item in enumerate(news_items):
        try:
            # 提取新闻项信息
            href = item.get("href", "")
            url = f"https://www.yicai.com{href}" if href.startswith("/") else href
            
            # 提取标题
            title_elem = item.select_one("h2")
            title = title_elem.text.strip() if title_elem else ""
            
            # 提取摘要
            summary_elem = item.select_one("p")
            summary = summary_elem.text.strip() if summary_elem else ""
            
            # 提取时间
            time_elem = item.select_one(".rightspan span:last-child")
            time_text = time_elem.text.strip() if time_elem else ""
            
            # 提取图片URL
            img_elem = item.select_one("img.u-img")
            image_url = img_elem.get("src", "") if img_elem else ""
            
            # 解析发布时间
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
            
            # 构建新闻项
            news_item = {
                "title": title,
                "url": url,
                "summary": summary,
                "image_url": image_url,
                "published_at": published_at.isoformat(),
                "time_text": time_text,
                "type": "news",
                "rank": index + 1
            }
            
            result.append(news_item)
            
        except Exception as e:
            logger.error(f"解析新闻项 {index} 时出错: {str(e)}")
    
    logger.info(f"成功解析 {len(result)} 条新闻")
    return result

def test_with_sample_html():
    """使用示例HTML测试解析功能"""
    # 从命令行参数获取HTML内容
    if len(sys.argv) > 1:
        html_file = sys.argv[1]
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
                
            if html_content:
                news_items = parse_yicai_html(html_content)
                if news_items:
                    # 打印前5条新闻项
                    logger.info("解析结果预览:")
                    for i, item in enumerate(news_items[:5]):
                        logger.info(f"新闻 {i+1}:")
                        logger.info(f"  标题: {item['title']}")
                        logger.info(f"  链接: {item['url']}")
                        logger.info(f"  发布时间: {item['published_at']}")
                        logger.info(f"  时间文本: {item['time_text']}")
                        if item['summary']:
                            logger.info(f"  摘要: {item['summary'][:100]}..." if len(item['summary']) > 100 else f"  摘要: {item['summary']}")
                        if item['image_url']:
                            logger.info(f"  图片URL: {item['image_url']}")
                        logger.info("")
                    
                    # 保存结果到JSON文件
                    output_file = "yicai_news_parsed.json"
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(news_items, f, ensure_ascii=False, indent=2)
                    
                    logger.info(f"成功解析 {len(news_items)} 条新闻，结果已保存到 {output_file}")
                else:
                    logger.warning("未解析到任何新闻")
            else:
                logger.error("HTML文件内容为空")
        except Exception as e:
            logger.error(f"处理HTML文件时出错: {str(e)}")
    else:
        # 使用提供的HTML示例
        logger.info("使用命令行提供的HTML示例...")
        sample_html = """
        <div class="m-con" id="newslist">
          <a href="/news/102543045.html" class="f-db" target="_blank">
            <div class="m-list m-list-1 f-cb">
              <div class="lef f-fl m-zoomin"><img class="u-img f-fl" src="https://imgcdn.yicai.com/uppics/slides/2025/03/4f388bd782a917254643ebfb7c1ad972.jpg" onerror="imgError(this)"></div>
              <div class="common"><h2>收盘丨A股三大指数全天弱势震荡，算力产业链午后崛起</h2><p>算力题材午后崛起，银行、电力板块逆势走强。全市场超4000只个股下跌。</p>
                <div class="author">
                  <div class="leftspan"></div>
                  <div class="rightspan"><span class="news_hot">0</span><span>5分钟前</span></div>
                </div>
              </div>
            </div>
          </a>
          <a href="/news/102542987.html" class="f-db" target="_blank">
            <div class="m-list m-list-1 f-cb">
              <div class="lef f-fl m-zoomin"><img class="u-img f-fl" src="https://imgcdn.yicai.com/uppics/slides/2025/03/8db3ff8bc55bfbc30b446978e4184551.jpg" onerror="imgError(this)"></div>
              <div class="common"><h2>中共中央政治局召开会议 中共中央总书记习近平主持会议</h2><p>要牢牢牵住责任制这个"牛鼻子"，强化大局意识，保持严的基调，敢于动真碰硬，持续发现问题，认真解决问题，提高对党中央生态文明建设决策部署的执行力。要强化督察队伍建设，加强规范管理，严明作风纪律。</p>
                <div class="author">
                  <div class="leftspan"></div>
                  <div class="rightspan"><span class="news_hot">0</span><span>28分钟前</span></div>
                </div>
              </div>
            </div>
          </a>
        </div>
        """
        
        news_items = parse_yicai_html(sample_html)
        
        if news_items:
            logger.info("解析结果预览:")
            for i, item in enumerate(news_items):
                logger.info(f"新闻 {i+1}:")
                logger.info(f"  标题: {item['title']}")
                logger.info(f"  链接: {item['url']}")
                logger.info(f"  发布时间: {item['published_at']}")
                logger.info(f"  时间文本: {item['time_text']}")
                if item['summary']:
                    logger.info(f"  摘要: {item['summary']}")
                if item['image_url']:
                    logger.info(f"  图片URL: {item['image_url']}")
                logger.info("")
        else:
            logger.warning("未解析到任何新闻")

if __name__ == "__main__":
    test_with_sample_html() 