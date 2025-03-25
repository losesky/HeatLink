import json
import logging
import datetime
from typing import List, Dict, Any

from worker.sources.base import NewsSource, NewsItemModel

logger = logging.getLogger(__name__)


class ZhihuHotNewsSource(NewsSource):
    """
    知乎热榜适配器
    """
    def __init__(self, **kwargs):
        super().__init__(
            source_id="zhihu",
            name="知乎热榜",
            category="social",
            country="CN",
            language="zh-CN",
            update_interval=600,  # 10分钟更新一次
            config=kwargs
        )
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        抓取知乎热榜
        """
        logger.info("Fetching Zhihu hot topics")
        
        url = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=50&desktop=true"
        
        try:
            # 获取 HTTP 客户端
            client = await self.http_client
            
            async with client.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch Zhihu hot topics: {response.status}")
                    return []
                
                data = await response.json()
                
                if not data or "data" not in data:
                    logger.error("Invalid response from Zhihu API")
                    return []
                
                items = []
                for item_data in data["data"]:
                    try:
                        target = item_data.get("target", {})
                        
                        # 获取标题
                        title = target.get("title", "")
                        if not title and "question" in target:
                            title = target.get("question", {}).get("title", "")
                        
                        # 获取URL
                        url = f"https://www.zhihu.com/question/{target.get('question', {}).get('id', '')}"
                        
                        # 获取摘要
                        excerpt = target.get("excerpt", "")
                        
                        # 获取热度
                        metrics = item_data.get("detail_text", "")
                        
                        # 创建新闻项
                        news_item = self.create_news_item(
                            id=self.generate_id(url, title),
                            title=title,
                            url=url,
                            summary=excerpt,
                            published_at=datetime.datetime.now(),
                            extra={
                                "metrics": metrics
                            }
                        )
                        
                        items.append(news_item)
                    except Exception as e:
                        logger.error(f"Error processing Zhihu item: {str(e)}")
                
                logger.info(f"Fetched {len(items)} items from Zhihu hot topics")
                return items
        
        except Exception as e:
            logger.error(f"Error fetching Zhihu hot topics: {str(e)}")
            return [] 