import logging
import datetime
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource

logger = logging.getLogger(__name__)


class WallStreetCNLiveNewsSource(APINewsSource):
    """
    华尔街见闻快讯适配器
    """
    
    def __init__(
        self,
        source_id: str = "wallstreetcn",
        name: str = "华尔街见闻快讯",
        api_url: str = "https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit=30",
        update_interval: int = 600,  # 10分钟
        cache_ttl: int = 300,  # 5分钟
        category: str = "finance",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://wallstreetcn.com/",
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
        解析华尔街见闻快讯API响应
        """
        try:
            news_items = []
            
            items = response.get("data", {}).get("items", [])
            for item in items:
                try:
                    # 获取ID
                    item_id = str(item.get("id", ""))
                    if not item_id:
                        continue
                    
                    # 获取标题和内容
                    title = item.get("title") or item.get("content_text", "")
                    if not title:
                        continue
                    
                    # 获取URL
                    url = item.get("uri", "")
                    if not url:
                        continue
                    
                    # 获取发布时间
                    display_time = item.get("display_time", 0)
                    published_at = None
                    if display_time:
                        try:
                            # 时间戳是秒级的
                            published_at = datetime.datetime.fromtimestamp(display_time)
                        except Exception as e:
                            logger.error(f"Error parsing timestamp {display_time}: {str(e)}")
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        content=item.get("content_text", ""),
                        summary=item.get("content_short", ""),
                        image_url=None,
                        published_at=published_at,
                        extra={
                            "is_top": False,
                            "mobile_url": url,  # 华尔街见闻的移动版URL与PC版相同
                            
                            
                            "display_time": display_time
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing WallStreetCN live news item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing WallStreetCN live news response: {str(e)}")
            return []


class WallStreetCNNewsSource(APINewsSource):
    """
    华尔街见闻文章适配器
    """
    
    def __init__(
        self,
        source_id: str = "wallstreetcn-news",
        name: str = "华尔街见闻文章",
        api_url: str = "https://api-one.wallstcn.com/apiv1/content/information-flow?channel=global-channel&accept=article&limit=30",
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "finance",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://wallstreetcn.com/",
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
        解析华尔街见闻文章API响应
        """
        try:
            news_items = []
            
            items = response.get("data", {}).get("items", [])
            for item in items:
                try:
                    # 跳过广告
                    if item.get("resource_type") == "ad":
                        continue
                    
                    # 跳过快讯
                    resource = item.get("resource", {})
                    if resource.get("type") == "live":
                        continue
                    
                    # 检查URI
                    uri = resource.get("uri", "")
                    if not uri:
                        continue
                    
                    # 获取ID
                    item_id = str(resource.get("id", ""))
                    if not item_id:
                        continue
                    
                    # 获取标题和内容
                    title = resource.get("title") or resource.get("content_short", "")
                    if not title:
                        continue
                    
                    # 获取发布时间
                    display_time = resource.get("display_time", 0)
                    published_at = None
                    if display_time:
                        try:
                            # 时间戳是秒级的
                            published_at = datetime.datetime.fromtimestamp(display_time)
                        except Exception as e:
                            logger.error(f"Error parsing timestamp {display_time}: {str(e)}")
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=uri,
                        content=resource.get("content_text", ""),
                        summary=resource.get("content_short", ""),
                        image_url=None,
                        published_at=published_at,
                        extra={
                            "is_top": False,
                            "mobile_url": uri,  # 华尔街见闻的移动版URL与PC版相同
                            
                            
                            "display_time": display_time
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing WallStreetCN news item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing WallStreetCN news response: {str(e)}")
            return []


class WallStreetCNHotNewsSource(APINewsSource):
    """
    华尔街见闻热门文章适配器
    """
    
    def __init__(
        self,
        source_id: str = "wallstreetcn-hot",
        name: str = "华尔街见闻热门",
        api_url: str = "https://api-one.wallstcn.com/apiv1/content/articles/hot?period=all",
        update_interval: int = 3600,  # 1小时
        cache_ttl: int = 1800,  # 30分钟
        category: str = "finance",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://wallstreetcn.com/",
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
        解析华尔街见闻热门文章API响应
        """
        try:
            news_items = []
            
            items = response.get("data", {}).get("day_items", [])
            for item in items:
                try:
                    # 获取ID
                    item_id = str(item.get("id", ""))
                    if not item_id:
                        continue
                    
                    # 获取标题
                    title = item.get("title", "")
                    if not title:
                        continue
                    
                    # 获取URL
                    url = item.get("uri", "")
                    if not url:
                        continue
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=None,
                        extra={"is_top": False, 
                            "mobile_url": url,  # 华尔街见闻的移动版URL与PC版相同
                            
                            
                            "display_time": None
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing WallStreetCN hot news item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing WallStreetCN hot news response: {str(e)}")
            return [] 