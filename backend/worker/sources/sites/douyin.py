import logging
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource

logger = logging.getLogger(__name__)


class DouyinHotNewsSource(APINewsSource):
    """
    抖音热搜适配器
    """
    
    def __init__(
        self,
        source_id: str = "douyin",
        name: str = "抖音热搜",
        api_url: str = "https://www.douyin.com/aweme/v1/web/hot/search/list/?device_platform=webapp&aid=6383&channel=channel_pc_web&detail_list=1",
        update_interval: int = 600,  # 10分钟
        cache_ttl: int = 300,  # 5分钟
        category: str = "social",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://www.douyin.com/",
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
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从抖音获取热搜
        需要先获取cookie
        """
        try:
            # 先访问抖音首页获取cookie
            cookie_response = await self.http_client.fetch(
                url="https://www.douyin.com/",
                method="GET",
                headers=self.headers,
                response_type="text"
            )
            
            # 从响应头中提取cookie
            if hasattr(cookie_response, "cookies"):
                cookies = cookie_response.cookies
                cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
                self.headers["Cookie"] = cookie_str
            
            # 获取热搜数据
            response = await self.http_client.fetch(
                url=self.api_url,
                method="GET",
                headers=self.headers,
                response_type="json"
            )
            
            # 解析响应
            return await self.parse_response(response)
            
        except Exception as e:
            logger.error(f"Error fetching Douyin hot search: {str(e)}")
            raise
    
    async def parse_response(self, response: Any) -> List[NewsItemModel]:
        """
        解析抖音热搜API响应
        """
        try:
            news_items = []
            
            word_list = response.get("data", {}).get("word_list", [])
            for item in word_list:
                try:
                    # 生成唯一ID
                    sentence_id = item.get("sentence_id", "")
                    item_id = self.generate_id(sentence_id)
                    
                    # 获取标题
                    title = item.get("word", "")
                    if not title:
                        continue
                    
                    # 获取URL
                    url = f"https://www.douyin.com/hot/{sentence_id}"
                    
                    # 获取热度值
                    hot_value = item.get("hot_value", "")
                    
                    # 获取发布时间
                    event_time = item.get("event_time", "")
                    published_at = self.parse_date(event_time) if event_time else None
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=item_id,
                        title=title,
                        url=url,
                        mobile_url=url,  # 抖音的移动版URL与PC版相同
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=published_at,
                        is_top=False,
                        extra={
                            "source_id": self.source_id,
                            "source_name": self.name,
                            "hot_value": hot_value
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing Douyin hot item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing Douyin hot response: {str(e)}")
            return [] 