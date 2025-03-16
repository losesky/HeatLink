import logging
import datetime
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.rest_api import RESTNewsSource

logger = logging.getLogger(__name__)


class CanKaoXiaoXiNewsSource(RESTNewsSource):
    """
    参考消息新闻源适配器
    """
    
    def __init__(
        self,
        source_id: str = "cankaoxiaoxi",
        name: str = "参考消息",
        api_url: str = "https://china.cankaoxiaoxi.com/json/channel/zhongguo/list.json",  # 默认使用中国频道
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "news",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://china.cankaoxiaoxi.com/"
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
            custom_parser=self.custom_parser
        )
        
        # 参考消息有多个频道，我们需要抓取所有频道
        self.channels = ["zhongguo", "guandian", "gj"]
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        重写fetch方法，抓取多个频道
        """
        news_items = []
        
        for channel in self.channels:
            try:
                # 构建频道URL
                channel_url = f"https://china.cankaoxiaoxi.com/json/channel/{channel}/list.json"
                
                # 发送请求
                response = await self.http_client.get(channel_url, headers=self.headers)
                
                # 解析响应
                if response.status == 200:
                    data = await response.json()
                    
                    # 使用自定义解析器处理数据
                    channel_items = self.custom_parser(data)
                    news_items.extend(channel_items)
                else:
                    logger.error(f"Failed to fetch data from {channel_url}, status: {response.status}")
            except Exception as e:
                logger.error(f"Error fetching data from channel {channel}: {str(e)}")
        
        # 按日期排序
        news_items.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.now(), reverse=True)
        
        return news_items
    
    def custom_parser(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """
        自定义解析器，处理参考消息的JSON数据
        """
        news_items = []
        
        try:
            # 获取新闻列表
            news_list = data.get("list", [])
            
            for item in news_list:
                try:
                    # 获取新闻数据
                    news_data = item.get("data", {})
                    
                    # 获取ID
                    item_id = news_data.get("id")
                    if not item_id:
                        continue
                    
                    # 获取标题
                    title = news_data.get("title")
                    if not title:
                        continue
                    
                    # 获取URL
                    url = news_data.get("url")
                    if not url:
                        continue
                    
                    # 获取发布时间
                    publish_time = news_data.get("publishTime")
                    published_at = None
                    if publish_time:
                        try:
                            # 参考消息的时间格式为：2023-04-01 12:34:56
                            published_at = datetime.datetime.strptime(publish_time, "%Y-%m-%d %H:%M:%S")
                        except Exception as e:
                            logger.error(f"Error parsing date {publish_time}: {str(e)}")
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=self.generate_id(item_id),
                        title=title,
                        url=url,
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=published_at,
                        extra={
                            "is_top": False,
                            "mobile_url": url,  # 参考消息的移动版URL与PC版相同
                            "source_id": self.source_id,
                            "source_name": self.name
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing CanKaoXiaoXi news item: {str(e)}")
                    continue
        except Exception as e:
            logger.error(f"Error parsing CanKaoXiaoXi response: {str(e)}")
        
        return news_items 