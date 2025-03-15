import json
import logging
import datetime
from typing import List, Dict, Any

from worker.sources.base import NewsSource, NewsItemModel

logger = logging.getLogger(__name__)


class ThePaperHotNewsSource(NewsSource):
    """
    澎湃新闻热榜适配器
    """
    def __init__(self, **kwargs):
        super().__init__(
            source_id="thepaper",
            name="澎湃新闻热榜",
            category="news",
            country="CN",
            language="zh-CN",
            update_interval=600,  # 10分钟更新一次
            config=kwargs
        )
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        抓取澎湃新闻热榜
        """
        logger.info("Fetching ThePaper hot news")
        
        url = "https://cache.thepaper.cn/contentapi/wwwIndex/rightSideLatest"
        
        try:
            async with self.http_client.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch ThePaper hot news: {response.status}")
                    return []
                
                data = await response.json()
                
                if not data or "data" not in data:
                    logger.error("Invalid response from ThePaper API")
                    return []
                
                items = []
                for item_data in data["data"]:
                    try:
                        # 获取标题
                        title = item_data.get("name", "")
                        if not title:
                            continue
                        
                        # 获取URL
                        contid = item_data.get("contId", "")
                        url = f"https://www.thepaper.cn/newsDetail_forward_{contid}"
                        
                        # 获取摘要
                        summary = item_data.get("summary", "")
                        
                        # 获取发布时间
                        publish_time = item_data.get("pubTime", 0)
                        if publish_time:
                            published_at = datetime.datetime.fromtimestamp(publish_time / 1000)
                        else:
                            published_at = datetime.datetime.now()
                        
                        # 获取图片
                        image_url = item_data.get("pic", "")
                        if image_url and not image_url.startswith("http"):
                            image_url = f"https://imagecloud.thepaper.cn/{image_url}"
                        
                        # 创建新闻项
                        news_item = NewsItemModel(
                            id=self.generate_id(url, title),
                            title=title,
                            url=url,
                            source_id=self.source_id,
                            source_name=self.name,
                            summary=summary,
                            image_url=image_url,
                            published_at=published_at,
                            extra={
                                "node_id": item_data.get("nodeId", ""),
                                "node_name": item_data.get("nodeName", ""),
                                "view_count": item_data.get("viewCount", 0)
                            }
                        )
                        
                        items.append(news_item)
                    except Exception as e:
                        logger.error(f"Error processing ThePaper item: {str(e)}")
                
                logger.info(f"Fetched {len(items)} items from ThePaper hot news")
                return items
        
        except Exception as e:
            logger.error(f"Error fetching ThePaper hot news: {str(e)}")
            return [] 