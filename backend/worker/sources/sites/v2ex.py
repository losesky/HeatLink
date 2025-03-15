import logging
import datetime
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource

logger = logging.getLogger(__name__)


class V2EXHotTopicsSource(APINewsSource):
    """
    V2EX热门话题适配器
    """
    
    def __init__(
        self,
        source_id: str = "v2ex",
        name: str = "V2EX热门",
        api_url: str = "https://www.v2ex.com/feed/create.json",
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "technology",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "application/json"
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
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从V2EX获取热门话题
        需要获取多个分类的feed
        """
        try:
            # 获取多个分类的feed
            categories = ["create", "ideas", "programmer", "share"]
            all_news_items = []
            
            for category in categories:
                api_url = f"https://www.v2ex.com/feed/{category}.json"
                
                # 获取API响应
                response = await self.http_client.fetch(
                    url=api_url,
                    method="GET",
                    headers=self.headers,
                    response_type="json"
                )
                
                # 解析响应
                news_items = await self.parse_response(response)
                all_news_items.extend(news_items)
            
            # 按发布时间排序
            all_news_items.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.min, reverse=True)
            
            return all_news_items
            
        except Exception as e:
            logger.error(f"Error fetching V2EX hot topics: {str(e)}")
            raise
    
    async def parse_response(self, response: Any) -> List[NewsItemModel]:
        """
        解析V2EX API响应
        """
        try:
            news_items = []
            
            for item in response.get("items", []):
                try:
                    # 获取ID
                    item_id = item.get("id", "")
                    if not item_id:
                        continue
                    
                    # 获取标题
                    title = item.get("title", "")
                    if not title:
                        continue
                    
                    # 获取URL
                    url = item.get("url", "")
                    if not url:
                        continue
                    
                    # 获取发布时间
                    published_at = None
                    date_str = item.get("date_modified") or item.get("date_published")
                    if date_str:
                        try:
                            published_at = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        except Exception as e:
                            logger.error(f"Error parsing date {date_str}: {str(e)}")
                    
                    # 获取内容
                    content_html = item.get("content_html", "")
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=item_id,
                        title=title,
                        url=url,
                        mobile_url=url,  # V2EX的移动版URL与PC版相同
                        content=content_html,
                        summary=None,
                        image_url=None,
                        published_at=published_at,
                        is_top=False,
                        extra={
                            "source_id": self.source_id,
                            "source_name": self.name
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing V2EX item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing V2EX response: {str(e)}")
            return [] 