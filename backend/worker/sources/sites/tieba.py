import logging
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource

logger = logging.getLogger(__name__)


class TiebaHotTopicSource(APINewsSource):
    """
    百度贴吧热门话题适配器
    """
    
    def __init__(
        self,
        source_id: str = "tieba",
        name: str = "贴吧热门话题",
        api_url: str = "https://tieba.baidu.com/hottopic/browse/topicList",
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "social",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://tieba.baidu.com/",
                "Accept": "application/json, text/plain, */*"
            }
        })
        
        super().__init__(
            source_id=source_id,
            name=name,
            api_url=api_url,
            update_interval=update_interval,
            cache_ttl=cache_ttl,
            category=category,
            country=country,
            language=language,
            config=config
        )
    
    async def parse_response(self, response: Any) -> List[NewsItemModel]:
        """
        解析贴吧热门话题API响应
        """
        try:
            news_items = []
            
            topic_list = response.get("data", {}).get("bang_topic", {}).get("topic_list", [])
            for item in topic_list:
                try:
                    # 获取话题ID
                    topic_id = item.get("topic_id", "")
                    if not topic_id:
                        continue
                    
                    # 生成唯一ID
                    item_id = self.generate_id(topic_id)
                    
                    # 获取话题名称
                    topic_name = item.get("topic_name", "")
                    if not topic_name:
                        continue
                    
                    # 获取URL
                    url = item.get("topic_url", "")
                    if not url:
                        continue
                    
                    # 获取创建时间
                    create_time = item.get("create_time", 0)
                    published_at = self.parse_date(str(create_time)) if create_time else None
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=item_id,
                        title=topic_name,
                        url=url,
                        mobile_url=url,  # 贴吧的移动版URL与PC版相同
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=published_at,
                        is_top=False,
                        extra={
                            "source_id": self.source_id,
                            "source_name": self.name,
                            "topic_id": topic_id
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing Tieba hot topic item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing Tieba hot topic response: {str(e)}")
            return [] 