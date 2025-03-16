import logging
import datetime
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.rest_api import RESTNewsSource

logger = logging.getLogger(__name__)


class KaoPuNewsSource(RESTNewsSource):
    """
    靠谱新闻源适配器
    """
    
    def __init__(
        self,
        source_id: str = "kaopu",
        name: str = "靠谱新闻",
        api_url: str = "https://kaopucdn.azureedge.net/jsondata/news_list_beta_hans_0.json",  # 默认使用第一个JSON文件
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
            custom_parser=self.custom_parser
        )
        
        # 靠谱新闻有多个JSON文件，我们需要抓取所有文件
        self.json_urls = [
            "https://kaopucdn.azureedge.net/jsondata/news_list_beta_hans_0.json",
            "https://kaopucdn.azureedge.net/jsondata/news_list_beta_hans_1.json"
        ]
        
        # 排除的发布者列表
        self.excluded_publishers = ["财新", "公视"]
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        重写fetch方法，抓取多个JSON文件
        """
        news_items = []
        
        for json_url in self.json_urls:
            try:
                # 发送请求
                response = await self.http_client.get(json_url, headers=self.headers)
                
                # 解析响应
                if response.status == 200:
                    data = await response.json()
                    
                    # 使用自定义解析器处理数据
                    file_items = self.custom_parser(data)
                    news_items.extend(file_items)
                else:
                    logger.error(f"Failed to fetch data from {json_url}, status: {response.status}")
            except Exception as e:
                logger.error(f"Error fetching data from URL {json_url}: {str(e)}")
        
        # 按日期排序
        news_items.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.now(), reverse=True)
        
        return news_items
    
    def custom_parser(self, data: List[Dict[str, Any]]) -> List[NewsItemModel]:
        """
        自定义解析器，处理靠谱新闻的JSON数据
        """
        news_items = []
        
        try:
            # 数据是一个列表
            for item in data:
                try:
                    # 获取发布者
                    publisher = item.get("publisher", "")
                    
                    # 排除特定发布者
                    if publisher in self.excluded_publishers:
                        continue
                    
                    # 获取链接
                    url = item.get("link")
                    if not url:
                        continue
                    
                    # 获取标题
                    title = item.get("title")
                    if not title:
                        continue
                    
                    # 获取描述
                    description = item.get("description", "")
                    
                    # 获取发布时间
                    pub_date_str = item.get("pubDate")
                    published_at = None
                    if pub_date_str:
                        try:
                            # 尝试解析ISO格式日期
                            published_at = datetime.datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                        except Exception as e:
                            logger.error(f"Error parsing date {pub_date_str}: {str(e)}")
                    
                    # 生成唯一ID
                    item_id = self.generate_id(url)
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=item_id,
                        title=title,
                        url=url,  # 靠谱新闻的移动版URL与PC版相同
                        content=None,
                        summary=description,
                        image_url=None,
                        published_at=published_at,
                        extra={"is_top": False, "mobile_url": url, 
                            "source_id": self.source_id,
                            "source_name": self.name,
                            "publisher": publisher,
                            "info": publisher
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing KaoPu news item: {str(e)}")
                    continue
        except Exception as e:
            logger.error(f"Error parsing KaoPu response: {str(e)}")
        
        return news_items 