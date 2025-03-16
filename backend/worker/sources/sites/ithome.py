import logging
import datetime
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

from worker.sources.base import NewsItemModel
from worker.sources.web import WebNewsSource

logger = logging.getLogger(__name__)


class ITHomeNewsSource(WebNewsSource):
    """
    IT之家新闻适配器
    """
    
    def __init__(
        self,
        source_id: str = "ithome",
        name: str = "IT之家",
        url: str = "https://www.ithome.com/list/",
        update_interval: int = 900,  # 15分钟
        cache_ttl: int = 600,  # 10分钟
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
        解析IT之家网页响应
        """
        try:
            news_items = []
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(response, 'html.parser')
            
            # 查找新闻列表
            news_list = soup.select("#list > div.fl > ul > li")
            
            for item in news_list:
                try:
                    # 获取链接和标题
                    link_element = item.select_one("a.t")
                    if not link_element:
                        continue
                    
                    url = link_element.get("href", "")
                    title = link_element.text.strip()
                    
                    # 获取日期
                    date_element = item.select_one("i")
                    date_text = date_element.text.strip() if date_element else ""
                    
                    # 检查是否为广告
                    is_ad = "lapin" in url or any(keyword in title for keyword in ["神券", "优惠", "补贴", "京东"])
                    if is_ad:
                        continue
                    
                    # 生成唯一ID
                    item_id = self.generate_id(url)
                    
                    # 解析日期
                    published_at = None
                    if date_text:
                        try:
                            # 尝试解析相对日期
                            now = datetime.datetime.now()
                            if "分钟前" in date_text:
                                minutes = int(date_text.replace("分钟前", ""))
                                published_at = now - datetime.timedelta(minutes=minutes)
                            elif "小时前" in date_text:
                                hours = int(date_text.replace("小时前", ""))
                                published_at = now - datetime.timedelta(hours=hours)
                            elif "昨天" in date_text:
                                time_part = date_text.replace("昨天", "").strip()
                                hour, minute = map(int, time_part.split(':'))
                                published_at = (now - datetime.timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
                            elif ":" in date_text:  # 今天的时间或完整日期时间
                                if "-" in date_text:  # 完整日期时间格式 (2025-03-16 01:07:18)
                                    try:
                                        published_at = datetime.datetime.strptime(date_text, "%Y-%m-%d %H:%M:%S")
                                    except ValueError:
                                        # 尝试没有秒的格式 (2025-03-16 01:07)
                                        published_at = datetime.datetime.strptime(date_text, "%Y-%m-%d %H:%M")
                                else:  # 只有时间 (01:07)
                                    hour, minute = map(int, date_text.split(':'))
                                    published_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        except Exception as e:
                            logger.error(f"Error parsing date {date_text}: {str(e)}")
                    
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
                            "date_text": date_text
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing IT Home news item: {str(e)}")
                    continue
            
            # 按发布时间排序
            news_items.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.min, reverse=True)
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing IT Home response: {str(e)}")
            return [] 