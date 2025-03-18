import json
import logging
import datetime
import re
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource

logger = logging.getLogger(__name__)


class WeiboHotNewsSource(APINewsSource):
    """
    微博热搜适配器
    """
    def __init__(
        self,
        source_id: str = "weibo",
        name: str = "微博热搜",
        api_url: str = "https://weibo.com/ajax/side/hotSearch",
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
                "Referer": "https://weibo.com/",
                "Accept": "application/json, text/plain, */*"
            },
            "data_path": "data.realtime"
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
        解析微博热搜API响应
        """
        try:
            news_items = []
            
            # 从配置中获取数据路径
            data_path = self.config.get("data_path", "data.realtime")
            
            # 解析数据路径
            path_parts = data_path.split(".")
            data = response
            for part in path_parts:
                if part in data:
                    data = data[part]
                else:
                    logger.error(f"Data path '{data_path}' not found in response")
                    return []
            
            # 确保数据是列表
            if not isinstance(data, list):
                logger.error(f"Data at path '{data_path}' is not a list")
                return []
            
            # 处理热搜列表
            for index, item in enumerate(data):
                try:
                    # 获取标题
                    title = item.get("word", "")
                    if not title:
                        continue
                    
                    # 获取链接
                    url = item.get("url", "")
                    if not url and title:
                        # 如果没有URL但有标题，构造一个搜索URL
                        url = f"https://s.weibo.com/weibo?q={title}"
                    
                    # 获取热度
                    hot = item.get("num", "")
                    
                    # 获取排名
                    rank = str(index + 1)
                    
                    # 判断是否置顶、新上榜等
                    is_top = item.get("is_top", 0) == 1
                    is_hot = item.get("is_hot", 0) == 1
                    is_new = item.get("is_new", 0) == 1
                    
                    # 创建唯一ID
                    unique_str = f"{self.source_id}:{title}:{url}"
                    item_id = self.generate_id(unique_str)
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
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
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing Weibo hot item: {str(e)}")
            
            logger.info(f"Parsed {len(news_items)} items from Weibo hot search API")
            return news_items
        
        except Exception as e:
            logger.error(f"Error parsing Weibo hot search API response: {str(e)}")
            return [] 