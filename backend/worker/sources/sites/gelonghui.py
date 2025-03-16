import logging
import datetime
import re
from typing import List, Dict, Any, Optional

from bs4 import BeautifulSoup

from worker.sources.base import NewsItemModel
from worker.sources.web import WebNewsSource

logger = logging.getLogger(__name__)


class GeLongHuiNewsSource(WebNewsSource):
    """
    格隆汇新闻源适配器
    """
    
    def __init__(
        self,
        source_id: str = "gelonghui",
        name: str = "格隆汇",
        url: str = "https://www.gelonghui.com/news/",
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
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析格隆汇网页响应
        """
        try:
            news_items = []
            base_url = "https://www.gelonghui.com"
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(response, 'html.parser')
            
            # 查找新闻列表
            news_list = soup.select(".article-content")
            
            for item in news_list:
                try:
                    # 获取链接和标题
                    link_element = item.select_one(".detail-right>a")
                    if not link_element:
                        continue
                    
                    url_path = link_element.get("href", "")
                    
                    # 获取标题
                    title_element = link_element.select_one("h2")
                    if not title_element:
                        continue
                    title = title_element.text.strip()
                    
                    # 获取信息（第一个span）
                    info_element = item.select_one(".time > span:nth-child(1)")
                    info = info_element.text.strip() if info_element else ""
                    
                    # 获取相对时间（第三个span）
                    time_element = item.select_one(".time > span:nth-child(3)")
                    relative_time = time_element.text.strip() if time_element else ""
                    
                    if not url_path or not title or not relative_time:
                        continue
                    
                    # 生成完整URL
                    url = f"{base_url}{url_path}"
                    
                    # 生成唯一ID
                    item_id = self.generate_id(url_path)
                    
                    # 解析相对日期
                    published_at = None
                    if relative_time:
                        try:
                            # 尝试解析相对日期
                            now = datetime.datetime.now()
                            if "分钟前" in relative_time:
                                minutes = int(relative_time.replace("分钟前", ""))
                                published_at = now - datetime.timedelta(minutes=minutes)
                            elif "小时前" in relative_time:
                                hours = int(relative_time.replace("小时前", ""))
                                published_at = now - datetime.timedelta(hours=hours)
                            elif "昨天" in relative_time:
                                time_part = relative_time.replace("昨天", "").strip()
                                if ":" in time_part:
                                    hour, minute = map(int, time_part.split(':'))
                                    published_at = (now - datetime.timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
                                else:
                                    published_at = now - datetime.timedelta(days=1)
                            elif ":" in relative_time:  # 今天的时间
                                hour, minute = map(int, relative_time.split(':'))
                                published_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                            elif re.match(r'\d{4}-\d{2}-\d{2}', relative_time):  # 完整日期
                                published_at = datetime.datetime.strptime(relative_time, "%Y-%m-%d")
                        except Exception as e:
                            logger.error(f"Error parsing date {relative_time}: {str(e)}")
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,  # 格隆汇的移动版URL与PC版相同
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=published_at,
                        extra={"is_top": False, "mobile_url": url, 
                            
                            
                            "info": info,
                            "relative_time": relative_time
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing GeLongHui news item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing GeLongHui response: {str(e)}")
            return [] 