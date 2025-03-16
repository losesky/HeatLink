import logging
import re
import datetime
from typing import List, Dict, Any, Optional

from bs4 import BeautifulSoup

from worker.sources.base import NewsItemModel
from worker.sources.web import WebNewsSource

logger = logging.getLogger(__name__)


class SolidotNewsSource(WebNewsSource):
    """
    Solidot（奇客）新闻源适配器
    """
    
    def __init__(
        self,
        source_id: str = "solidot",
        name: str = "奇客",
        url: str = "https://www.solidot.org",
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
        解析Solidot网页响应
        """
        try:
            news_items = []
            base_url = "https://www.solidot.org"
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(response, 'html.parser')
            
            # 查找新闻列表
            news_list = soup.select(".block_m")
            
            for item in news_list:
                try:
                    # 获取链接和标题
                    link_element = item.select_one(".bg_htit a:last-child")
                    if not link_element:
                        continue
                    
                    url_path = link_element.get("href", "")
                    title = link_element.text.strip()
                    
                    # 获取发布时间
                    date_element = item.select_one(".talk_time")
                    if not date_element:
                        continue
                    
                    date_text = date_element.text.strip()
                    date_match = re.search(r'发表于(.*?分)', date_text)
                    if not date_match:
                        continue
                    
                    date_raw = date_match.group(1)
                    date_str = date_raw.replace('年', '-').replace('月', '-').replace('时', ':').replace('分', '').replace('日', '')
                    
                    if not url_path or not title or not date_str:
                        continue
                    
                    # 生成完整URL
                    url = f"{base_url}{url_path}"
                    
                    # 生成唯一ID
                    item_id = self.generate_id(url_path)
                    
                    # 解析日期
                    published_at = None
                    try:
                        # 尝试解析相对日期
                        now = datetime.datetime.now()
                        if ":" in date_str:  # 包含时间
                            if "-" in date_str:  # 包含日期
                                # 完整日期时间格式：2023-04-01 12:34
                                published_at = datetime.datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M")
                            else:
                                # 只有时间格式：12:34
                                hour, minute = map(int, date_str.strip().split(':'))
                                published_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    except Exception as e:
                        logger.error(f"Error parsing date {date_str}: {str(e)}")
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=item_id,
                        title=title,
                        url=url,  # Solidot的移动版URL与PC版相同
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=published_at,
                        extra={"is_top": False, "mobile_url": url, 
                            "source_id": self.source_id,
                            "source_name": self.name,
                            "relative_date": date_raw
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing Solidot news item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing Solidot response: {str(e)}")
            return [] 