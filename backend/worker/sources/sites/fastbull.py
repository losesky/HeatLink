import logging
import re
import datetime
from typing import List, Dict, Any, Optional

from bs4 import BeautifulSoup

from worker.sources.base import NewsItemModel
from worker.sources.web import WebNewsSource

logger = logging.getLogger(__name__)


class FastBullNewsSource(WebNewsSource):
    """
    快牛新闻源适配器基类
    """
    
    def __init__(
        self,
        source_id: str,
        name: str,
        url: str,
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
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        })
        
        super().__init__(
            source_id=source_id,
            name=name,
            url=url,
            update_interval=update_interval,
            cache_ttl=cache_ttl,
            category=category,
            country=country,
            language=language,
            config=config
        )


class FastBullExpressNewsSource(FastBullNewsSource):
    """
    快牛快讯适配器
    """
    
    def __init__(
        self,
        source_id: str = "fastbull-express",
        name: str = "快牛快讯",
        url: str = "https://www.fastbull.com/cn/express-news",
        **kwargs
    ):
        super().__init__(
            source_id=source_id,
            name=name,
            url=url,
            **kwargs
        )
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析快牛快讯网页响应
        """
        try:
            news_items = []
            base_url = "https://www.fastbull.com"
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(response, 'html.parser')
            
            # 查找新闻列表
            news_list = soup.select(".news-list")
            
            for item in news_list:
                try:
                    # 获取链接和标题
                    link_element = item.select_one(".title_name")
                    if not link_element:
                        continue
                    
                    url_path = link_element.get("href", "")
                    title_text = link_element.text.strip()
                    
                    # 提取标题中的【】内容
                    title_match = re.search(r'【(.+)】', title_text)
                    title = title_match.group(1) if title_match else title_text
                    
                    # 如果提取的标题太短，使用原始标题
                    if len(title) < 4:
                        title = title_text
                    
                    # 获取日期时间戳
                    date_timestamp = item.get("data-date")
                    
                    if not url_path or not title or not date_timestamp:
                        continue
                    
                    # 生成完整URL
                    url = f"{base_url}{url_path}"
                    
                    # 生成唯一ID
                    item_id = self.generate_id(url_path)
                    
                    # 解析日期
                    published_at = None
                    try:
                        # 时间戳是毫秒级的
                        timestamp_ms = int(date_timestamp)
                        published_at = datetime.datetime.fromtimestamp(timestamp_ms / 1000)
                    except Exception as e:
                        logger.error(f"Error parsing timestamp {date_timestamp}: {str(e)}")
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=item_id,
                        title=title,
                        url=url,  # 快牛的移动版URL与PC版相同
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=published_at,
                        extra={"is_top": False, "mobile_url": url, 
                            "source_id": self.source_id,
                            "source_name": self.name,
                            "original_title": title_text
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing FastBull express news item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing FastBull express response: {str(e)}")
            return []


class FastBullGeneralNewsSource(FastBullNewsSource):
    """
    快牛一般新闻适配器
    """
    
    def __init__(
        self,
        source_id: str = "fastbull-news",
        name: str = "快牛新闻",
        url: str = "https://www.fastbull.com/cn/news",
        **kwargs
    ):
        super().__init__(
            source_id=source_id,
            name=name,
            url=url,
            **kwargs
        )
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析快牛一般新闻网页响应
        """
        try:
            news_items = []
            base_url = "https://www.fastbull.com"
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(response, 'html.parser')
            
            # 查找新闻列表
            news_list = soup.select(".trending_type")
            
            for item in news_list:
                try:
                    # 获取链接
                    url_path = item.get("href", "")
                    
                    # 获取标题
                    title_element = item.select_one(".title")
                    if not title_element:
                        continue
                    title = title_element.text.strip()
                    
                    # 获取日期元素
                    date_element = item.select_one("[data-date]")
                    if not date_element:
                        continue
                    
                    # 获取日期时间戳
                    date_timestamp = date_element.get("data-date")
                    if not date_timestamp:
                        continue
                    
                    if not url_path or not title:
                        continue
                    
                    # 生成完整URL
                    url = f"{base_url}{url_path}"
                    
                    # 生成唯一ID
                    item_id = self.generate_id(url_path)
                    
                    # 解析日期
                    published_at = None
                    try:
                        # 时间戳是毫秒级的
                        timestamp_ms = int(date_timestamp)
                        published_at = datetime.datetime.fromtimestamp(timestamp_ms / 1000)
                    except Exception as e:
                        logger.error(f"Error parsing timestamp {date_timestamp}: {str(e)}")
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=item_id,
                        title=title,
                        url=url,  # 快牛的移动版URL与PC版相同
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=published_at,
                        extra={"is_top": False, "mobile_url": url, 
                            "source_id": self.source_id,
                            "source_name": self.name
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing FastBull news item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing FastBull news response: {str(e)}")
            return [] 