import logging
import json
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource
from worker.utils.http_client import http_client

logger = logging.getLogger(__name__)


class BilibiliHotNewsSource(APINewsSource):
    """
    B站热搜适配器
    """
    
    def __init__(
        self,
        source_id: str = "bilibili",
        name: str = "B站热搜",
        api_url: str = "https://s.search.bilibili.com/main/hotword?limit=30",
        update_interval: int = 600,  # 10分钟
        cache_ttl: int = 300,  # 5分钟
        category: str = "video",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            },
            "response_type": "text"  # Use text response type instead of json
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
        从API获取新闻，重写父类方法以处理特殊的JSON响应
        """
        logger.info(f"Fetching news from API: {self.api_url}")
        
        try:
            # 获取API响应（作为文本）
            response_text = await http_client.fetch(
                url=self.api_url,
                method="GET",
                headers=self.headers,
                params=self.params,
                json_data=self.json_data,
                response_type="text"  # Always get as text
            )
            
            # 手动解析JSON
            try:
                response_json = json.loads(response_text)
                # 解析响应
                news_items = await self.parse_response(response_json)
                
                logger.info(f"Fetched {len(news_items)} news items from API: {self.api_url}")
                return news_items
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON from {self.api_url}: {str(e)}")
                logger.debug(f"First 200 chars of response: {response_text[:200]}")
                raise
            
        except Exception as e:
            logger.error(f"Error fetching API news from {self.api_url}: {str(e)}")
            raise
    
    async def parse_response(self, response: Any) -> List[NewsItemModel]:
        """
        解析B站热搜API响应
        """
        try:
            news_items = []
            
            for item in response.get("list", []):
                try:
                    # 生成唯一ID
                    item_id = self.generate_id(item.get("keyword", ""))
                    
                    # 获取标题
                    title = item.get("show_name", "")
                    if not title:
                        continue
                    
                    # 获取URL
                    keyword = item.get("keyword", "")
                    url = f"https://search.bilibili.com/all?keyword={keyword}"
                    
                    # 获取图标
                    icon = item.get("icon", "")
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        content=None,
                        summary=None,
                        image_url=icon,
                        published_at=None,
                        extra={
                            "rank": item.get("rank", 0),
                            "heat_score": item.get("heat_score", 0),
                            "mobile_url": url
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing Bilibili hot item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing Bilibili hot response: {str(e)}")
            return [] 