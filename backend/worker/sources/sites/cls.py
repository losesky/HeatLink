import logging
import datetime
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.rest_api import RESTNewsSource

logger = logging.getLogger(__name__)


class CLSNewsSource(RESTNewsSource):
    """
    财联社新闻源适配器
    """
    
    def __init__(
        self,
        source_id: str = "cls",
        name: str = "财联社",
        api_url: str = "https://www.cls.cn/api/sw?app=CailianpressWeb&os=web&sv=7.7.5&sign=6c3c9e7b3b7e4b503dbd8a8c2f31b4c5",
        update_interval: int = 300,  # 5分钟
        cache_ttl: int = 180,  # 3分钟
        category: str = "finance",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://www.cls.cn/telegraph",
                "Content-Type": "application/json",
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
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        重写fetch方法，使用POST请求
        """
        try:
            # 构建请求体
            request_body = {
                "type": "telegram",
                "page": 1,
                "rn": 20,  # 获取20条数据
                "os": "web"
            }
            
            # 发送POST请求
            response = await self.http_client.post(self.api_url, json=request_body, headers=self.headers)
            
            # 解析响应
            if response.status == 200:
                data = await response.json()
                
                # 使用自定义解析器处理数据
                return self.custom_parser(data)
            else:
                logger.error(f"Failed to fetch data from {self.api_url}, status: {response.status}")
                return []
        except Exception as e:
            logger.error(f"Error fetching data from {self.api_url}: {str(e)}")
            return []
    
    def custom_parser(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """
        自定义解析器，处理财联社的JSON数据
        """
        news_items = []
        
        try:
            # 获取数据列表
            data_list = data.get("data", {}).get("roll_data", [])
            
            for item in data_list:
                try:
                    # 获取ID
                    item_id = item.get("id")
                    if not item_id:
                        continue
                    
                    # 获取标题
                    title = item.get("title") or item.get("content")
                    if not title:
                        continue
                    
                    # 获取内容
                    content = item.get("content", "")
                    
                    # 获取URL
                    url = f"https://www.cls.cn/detail/{item_id}"
                    
                    # 获取发布时间
                    published_at = None
                    publish_time = item.get("ctime")
                    if publish_time:
                        try:
                            # 财联社的时间戳是秒级的
                            published_at = datetime.datetime.fromtimestamp(int(publish_time))
                        except Exception as e:
                            logger.error(f"Error parsing timestamp {publish_time}: {str(e)}")
                    
                    # 获取标签
                    tag = item.get("tag_name", "")
                    
                    # 获取重要性
                    importance = item.get("level", 0)
                    is_top = importance > 0
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=str(item_id),
                        title=title,
                        url=url,
                        mobile_url=url,  # 财联社的移动版URL与PC版相同
                        content=content,
                        summary=content,
                        image_url=None,
                        published_at=published_at,
                        extra={
                            "is_top": is_top,
                            "source_id": self.source_id,
                            "source_name": self.name,
                            "tag": tag,
                            "importance": importance,
                            "info": tag
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing CLS news item: {str(e)}")
                    continue
            
            # 按发布时间排序
            news_items.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.now(), reverse=True)
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing CLS response: {str(e)}")
            return []


class CLSArticleNewsSource(CLSNewsSource):
    """
    财联社文章适配器
    """
    
    def __init__(
        self,
        source_id: str = "cls-article",
        name: str = "财联社文章",
        api_url: str = "https://www.cls.cn/api/sw?app=CailianpressWeb&os=web&sv=7.7.5&sign=6c3c9e7b3b7e4b503dbd8a8c2f31b4c5",
        **kwargs
    ):
        super().__init__(
            source_id=source_id,
            name=name,
            api_url=api_url,
            **kwargs
        )
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        重写fetch方法，使用POST请求获取文章
        """
        try:
            # 构建请求体
            request_body = {
                "type": "web_article",
                "page": 1,
                "rn": 20,  # 获取20条数据
                "os": "web"
            }
            
            # 发送POST请求
            response = await self.http_client.post(self.api_url, json=request_body, headers=self.headers)
            
            # 解析响应
            if response.status == 200:
                data = await response.json()
                
                # 使用自定义解析器处理数据
                return self.parse_article_data(data)
            else:
                logger.error(f"Failed to fetch article data from {self.api_url}, status: {response.status}")
                return []
        except Exception as e:
            logger.error(f"Error fetching article data from {self.api_url}: {str(e)}")
            return []
    
    def parse_article_data(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """
        解析财联社文章数据
        """
        news_items = []
        
        try:
            # 获取数据列表
            data_list = data.get("data", {}).get("roll_data", [])
            
            for item in data_list:
                try:
                    # 获取ID
                    item_id = item.get("id")
                    if not item_id:
                        continue
                    
                    # 获取标题
                    title = item.get("title")
                    if not title:
                        continue
                    
                    # 获取摘要
                    summary = item.get("brief", "")
                    
                    # 获取URL
                    url = f"https://www.cls.cn/detail/{item_id}"
                    
                    # 获取发布时间
                    published_at = None
                    publish_time = item.get("ctime")
                    if publish_time:
                        try:
                            # 财联社的时间戳是秒级的
                            published_at = datetime.datetime.fromtimestamp(int(publish_time))
                        except Exception as e:
                            logger.error(f"Error parsing timestamp {publish_time}: {str(e)}")
                    
                    # 获取标签
                    tag = item.get("tag_name", "")
                    
                    # 获取图片
                    image_url = item.get("thumbnails", [None])[0]
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=str(item_id),
                        title=title,
                        url=url,
                        mobile_url=url,  # 财联社的移动版URL与PC版相同
                        content=None,
                        summary=summary,
                        image_url=image_url,
                        published_at=published_at,
                        extra={
                            "is_top": False,
                            "source_id": self.source_id,
                            "source_name": self.name,
                            "content_id": item_id,
                            "remark": tag
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing CLS article item: {str(e)}")
                    continue
            
            # 按发布时间排序
            news_items.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.now(), reverse=True)
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing CLS article response: {str(e)}")
            return [] 