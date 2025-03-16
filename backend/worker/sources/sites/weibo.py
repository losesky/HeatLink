import json
import logging
import datetime
import re
from typing import List, Dict, Any

from bs4 import BeautifulSoup
from worker.sources.base import NewsSource, NewsItemModel

logger = logging.getLogger(__name__)


class WeiboHotNewsSource(NewsSource):
    """
    微博热搜适配器
    """
    def __init__(self, **kwargs):
        super().__init__(
            source_id="weibo",
            name="微博热搜",
            category="social",
            country="CN",
            language="zh-CN",
            update_interval=600,  # 10分钟更新一次
            config=kwargs
        )
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        抓取微博热搜
        """
        logger.info("Fetching Weibo hot search")
        
        url = "https://s.weibo.com/top/summary"
        
        try:
            async with self.http_client.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch Weibo hot search: {response.status}")
                    return []
                
                html = await response.text()
                
                # 使用BeautifulSoup解析HTML
                soup = BeautifulSoup(html, "html.parser")
                
                # 查找热搜列表
                hot_list = soup.select("div.data > table > tbody > tr")
                
                items = []
                for item in hot_list:
                    try:
                        # 跳过表头
                        if not item.select_one("td.td-01"):
                            continue
                        
                        # 获取排名
                        rank = item.select_one("td.td-01").text.strip()
                        
                        # 获取标题和链接
                        title_element = item.select_one("td.td-02 > a")
                        if not title_element:
                            continue
                        
                        title = title_element.text.strip()
                        path = title_element.get("href", "")
                        url = f"https://s.weibo.com{path}" if path else ""
                        
                        # 获取热度
                        hot_element = item.select_one("td.td-02 > span")
                        hot = hot_element.text.strip() if hot_element else ""
                        
                        # 判断是否置顶或新上榜
                        is_top = bool(item.select_one("td.td-01 > i.icon-top"))
                        is_new = bool(item.select_one("td.td-02 > i.icon-new"))
                        is_hot = bool(item.select_one("td.td-02 > i.icon-hot"))
                        
                        # 创建新闻项
                        news_item = self.create_news_item(
                            id=self.generate_id(url, title),
                            title=title,
                            url=url,
                            published_at=datetime.datetime.now(),
                            extra={
                                "rank": rank,
                                "hot": hot,
                                "is_top": is_top,
                                "is_new": is_new,
                                "is_hot": is_hot
                            }
                        )
                        
                        items.append(news_item)
                    except Exception as e:
                        logger.error(f"Error processing Weibo hot item: {str(e)}")
                
                logger.info(f"Fetched {len(items)} items from Weibo hot search")
                return items
        
        except Exception as e:
            logger.error(f"Error fetching Weibo hot search: {str(e)}")
            return [] 