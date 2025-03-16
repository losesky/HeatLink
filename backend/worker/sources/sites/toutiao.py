import logging
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource

logger = logging.getLogger(__name__)


class ToutiaoHotNewsSource(APINewsSource):
    """
    今日头条热搜适配器
    """
    
    def __init__(
        self,
        source_id: str = "toutiao",
        name: str = "今日头条热搜",
        api_url: str = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
        update_interval: int = 600,  # 10分钟
        cache_ttl: int = 300,  # 5分钟
        category: str = "news",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://www.toutiao.com/",
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
        解析今日头条热搜API响应
        """
        try:
            news_items = []
            
            for item in response.get("data", []):
                try:
                    # 生成唯一ID
                    cluster_id = item.get("ClusterIdStr", "")
                    item_id = self.generate_id(cluster_id)
                    
                    # 获取标题
                    title = item.get("Title", "")
                    if not title:
                        continue
                    
                    # 获取URL
                    url = f"https://www.toutiao.com/trending/{cluster_id}/"
                    
                    # 获取热度值
                    hot_value = item.get("HotValue", "")
                    
                    # 获取图标
                    image_url = None
                    if item.get("LabelUri") and item["LabelUri"].get("url"):
                        image_url = item["LabelUri"]["url"]
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,  # 头条的移动版URL与PC版相同
                        content=None,
                        summary=None,
                        image_url=image_url,
                        published_at=None,
                        extra={"is_top": False, "mobile_url": url, 
                            "hot_value": hot_value
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing Toutiao hot item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing Toutiao hot response: {str(e)}")
            return [] 