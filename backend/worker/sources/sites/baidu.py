import json
import logging
import datetime
import re
from typing import List, Dict, Any

from bs4 import BeautifulSoup
from worker.sources.base import NewsSource, NewsItemModel

logger = logging.getLogger(__name__)


class BaiduHotNewsSource(NewsSource):
    """
    百度热搜适配器
    """
    def __init__(self, **kwargs):
        super().__init__(
            source_id="baidu",
            name="百度热搜",
            category="search",
            country="CN",
            language="zh-CN",
            update_interval=600,  # 10分钟更新一次
            config=kwargs
        )
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        抓取百度热搜
        """
        logger.info("Fetching Baidu hot search")
        
        url = "https://top.baidu.com/board?tab=realtime"
        
        try:
            # 获取 HTTP 客户端
            client = await self.http_client
            async with client.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch Baidu hot search: {response.status}")
                    return []
                
                html = await response.text()
                
                # 使用正则表达式提取JSON数据
                pattern = r'<!--\s*s-data:\s*({.*})\s*-->'
                match = re.search(pattern, html)
                
                if not match:
                    logger.error("Failed to extract data from Baidu hot search")
                    return []
                
                try:
                    data = json.loads(match.group(1))
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON data from Baidu hot search: {str(e)}")
                    return []
                
                # 提取热搜列表
                cards = data.get("data", {}).get("cards", [])
                if not cards:
                    logger.error("No cards found in Baidu hot search data")
                    return []
                
                # 获取第一个卡片的内容
                content = cards[0].get("content", [])
                
                items = []
                for item in content:
                    try:
                        # 获取标题
                        title = item.get("query", "")
                        if not title:
                            continue
                        
                        # 获取URL
                        url = item.get("url", "")
                        if not url:
                            url = f"https://www.baidu.com/s?wd={title}"
                        
                        # 获取摘要
                        desc = item.get("desc", "")
                        
                        # 获取热度
                        hot_score = item.get("hotScore", "")
                        
                        # 获取图片
                        image_url = item.get("img", "")
                        
                        # 创建新闻项
                        news_item = self.create_news_item(
                            id=self.generate_id(url, title),
                            title=title,
                            url=url,
                            summary=desc,
                            image_url=image_url,
                            published_at=datetime.datetime.now(),
                            extra={
                                "hot_score": hot_score,
                                "index": item.get("index", 0)
                            }
                        )
                        
                        items.append(news_item)
                    except Exception as e:
                        logger.error(f"Error processing Baidu hot item: {str(e)}")
                
                logger.info(f"Fetched {len(items)} items from Baidu hot search")
                return items
        
        except Exception as e:
            logger.error(f"Error fetching Baidu hot search: {str(e)}")
            return [] 