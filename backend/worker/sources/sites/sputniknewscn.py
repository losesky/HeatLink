import logging
import datetime
from typing import List, Dict, Any, Optional

from bs4 import BeautifulSoup

from worker.sources.base import NewsItemModel
from worker.sources.web import WebNewsSource

logger = logging.getLogger(__name__)


class SputnikNewsCNSource(WebNewsSource):
    """
    俄罗斯卫星通讯社中文网新闻源适配器
    """
    
    def __init__(
        self,
        source_id: str = "sputniknewscn",
        name: str = "卫星通讯社",
        url: str = "https://sputniknews.cn/services/widget/lenta/",
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "news",
        country: str = "RU",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://sputniknews.cn/"
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
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析俄罗斯卫星通讯社中文网网页响应
        """
        try:
            news_items = []
            base_url = "https://sputniknews.cn"
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(response, 'html.parser')
            
            # 查找新闻列表
            news_list = soup.select(".lenta__item")
            
            for item in news_list:
                try:
                    # 获取链接元素
                    link_element = item.select_one("a")
                    if not link_element:
                        continue
                    
                    # 获取URL
                    url_path = link_element.get("href", "")
                    
                    # 获取标题
                    title_element = link_element.select_one(".lenta__item-text")
                    if not title_element:
                        continue
                    title = title_element.text.strip()
                    
                    # 获取日期时间戳
                    date_element = link_element.select_one(".lenta__item-date")
                    if not date_element:
                        continue
                    
                    unix_timestamp = date_element.get("data-unixtime")
                    if not unix_timestamp:
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
                        # 卫星通讯社的时间戳是秒级的，需要转换为毫秒级
                        timestamp_ms = int(unix_timestamp) * 1000
                        published_at = datetime.datetime.fromtimestamp(timestamp_ms / 1000)
                    except Exception as e:
                        logger.error(f"Error parsing timestamp {unix_timestamp}: {str(e)}")
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,  # 卫星通讯社的移动版URL与PC版相同
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=published_at,
                        extra={"is_top": False, "mobile_url": url, 
                            
                            
                            "timestamp": unix_timestamp
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing SputnikNewsCN news item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing SputnikNewsCN response: {str(e)}")
            return [] 