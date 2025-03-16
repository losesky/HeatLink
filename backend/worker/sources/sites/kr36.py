import logging
import datetime
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

from worker.sources.base import NewsItemModel
from worker.sources.web import WebNewsSource

logger = logging.getLogger(__name__)


class Kr36NewsSource(WebNewsSource):
    """
    36氪快讯适配器
    """
    
    def __init__(
        self,
        source_id: str = "36kr",
        name: str = "36氪快讯",
        url: str = "https://www.36kr.com/newsflashes",
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
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析36氪快讯网页响应
        """
        try:
            news_items = []
            base_url = "https://www.36kr.com"
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(response, 'html.parser')
            
            # 查找快讯列表
            news_list = soup.select(".newsflash-item")
            
            for item in news_list:
                try:
                    # 获取链接和标题
                    link_element = item.select_one("a.item-title")
                    if not link_element:
                        continue
                    
                    url_path = link_element.get("href", "")
                    title = link_element.text.strip()
                    
                    # 获取相对日期
                    date_element = item.select_one(".time")
                    relative_date = date_element.text.strip() if date_element else ""
                    
                    if not url_path or not title or not relative_date:
                        continue
                    
                    # 生成完整URL
                    url = f"{base_url}{url_path}"
                    
                    # 生成唯一ID
                    item_id = self.generate_id(url_path)
                    
                    # 解析相对日期
                    published_at = None
                    if relative_date:
                        try:
                            # 尝试解析相对日期
                            now = datetime.datetime.now()
                            if "分钟前" in relative_date:
                                minutes = int(relative_date.replace("分钟前", ""))
                                published_at = now - datetime.timedelta(minutes=minutes)
                            elif "小时前" in relative_date:
                                hours = int(relative_date.replace("小时前", ""))
                                published_at = now - datetime.timedelta(hours=hours)
                            elif "昨天" in relative_date:
                                time_part = relative_date.replace("昨天", "").strip()
                                hour, minute = map(int, time_part.split(':'))
                                published_at = (now - datetime.timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
                            elif ":" in relative_date:  # 今天的时间
                                hour, minute = map(int, relative_date.split(':'))
                                published_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        except Exception as e:
                            logger.error(f"Error parsing date {relative_date}: {str(e)}")
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=item_id,
                        title=title,
                        url=url,
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=published_at,
                        extra={"is_top": False, "mobile_url": None, 
                            "source_id": self.source_id,
                            "source_name": self.name,
                            "relative_date": relative_date
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing 36Kr news item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing 36Kr response: {str(e)}")
            return [] 