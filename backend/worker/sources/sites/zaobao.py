import logging
import re
import datetime
from typing import List, Dict, Any, Optional

from bs4 import BeautifulSoup

from worker.sources.base import NewsItemModel
from worker.sources.web import WebNewsSource

logger = logging.getLogger(__name__)


class ZaoBaoNewsSource(WebNewsSource):
    """
    早报新闻源适配器
    """
    
    def __init__(
        self,
        source_id: str = "zaobao",
        name: str = "早报",
        url: str = "https://www.zaochenbao.com/realtime/",
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
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            },
            "encoding": "gb2312"  # 早报网站使用GB2312编码
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
    
    async def fetch_content(self) -> str:
        """
        重写fetch_content方法，处理GB2312编码
        """
        try:
            response = await self.http_client.get(self.url, headers=self.headers)
            if response.status == 200:
                # 获取原始二进制内容
                content = await response.read()
                
                # 使用GB2312解码
                encoding = self.config.get("encoding", "utf-8")
                try:
                    decoded_content = content.decode(encoding)
                except UnicodeDecodeError:
                    logger.warning(f"Failed to decode with {encoding}, falling back to utf-8")
                    decoded_content = content.decode("utf-8", errors="replace")
                
                return decoded_content
            else:
                logger.error(f"Failed to fetch content from {self.url}, status: {response.status}")
                return ""
        except Exception as e:
            logger.error(f"Error fetching content from {self.url}: {str(e)}")
            return ""
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析早报网页响应
        """
        try:
            news_items = []
            base_url = "https://www.zaochenbao.com"
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(response, 'html.parser')
            
            # 查找新闻列表
            news_list = soup.select("div.list-block>a.item")
            
            for item in news_list:
                try:
                    # 获取链接
                    url_path = item.get("href", "")
                    if not url_path:
                        continue
                    
                    # 获取标题
                    title_element = item.select_one(".eps")
                    if not title_element:
                        continue
                    title = title_element.text.strip()
                    
                    # 获取日期
                    date_element = item.select_one(".pdt10")
                    if not date_element:
                        continue
                    date_text = date_element.text.strip()
                    date_text = date_text.replace("-\s", " ")
                    
                    if not url_path or not title or not date_text:
                        continue
                    
                    # 生成完整URL
                    url = f"{base_url}{url_path}"
                    
                    # 生成唯一ID
                    item_id = self.generate_id(url_path)
                    
                    # 解析日期
                    published_at = None
                    try:
                        # 尝试解析日期
                        # 早报的日期格式通常为：2023-04-01 12:34
                        published_at = datetime.datetime.strptime(date_text.strip(), "%Y-%m-%d %H:%M")
                    except Exception as e:
                        logger.error(f"Error parsing date {date_text}: {str(e)}")
                        
                        # 尝试其他可能的日期格式
                        try:
                            # 尝试解析相对日期
                            now = datetime.datetime.now()
                            if ":" in date_text:  # 包含时间
                                if "-" in date_text:  # 包含日期
                                    # 尝试不同的日期格式
                                    for fmt in ["%Y-%m-%d %H:%M", "%m-%d %H:%M"]:
                                        try:
                                            if fmt == "%m-%d %H:%M":
                                                dt = datetime.datetime.strptime(date_text.strip(), fmt)
                                                published_at = dt.replace(year=now.year)
                                            else:
                                                published_at = datetime.datetime.strptime(date_text.strip(), fmt)
                                            break
                                        except:
                                            continue
                                else:
                                    # 只有时间格式：12:34
                                    hour, minute = map(int, date_text.strip().split(':'))
                                    published_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        except Exception as e2:
                            logger.error(f"Error parsing alternative date format {date_text}: {str(e2)}")
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=item_id,
                        title=title,
                        url=url,
                        mobile_url=url,  # 早报的移动版URL与PC版相同
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=published_at,
                        is_top=False,
                        extra={
                            "source_id": self.source_id,
                            "source_name": self.name,
                            "date_text": date_text
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing ZaoBao news item: {str(e)}")
                    continue
            
            # 按日期排序
            news_items.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.now(), reverse=True)
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing ZaoBao response: {str(e)}")
            return [] 