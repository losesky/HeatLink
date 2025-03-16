import logging
import re
import datetime
from typing import List, Dict, Any, Optional

from bs4 import BeautifulSoup

from worker.sources.base import NewsItemModel
from worker.sources.web import WebNewsSource
from worker.utils.http_client import http_client

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
            client = await self.http_client
            
            async with client.get(
                url=self.url,
                headers=self.headers
            ) as response:
                response.raise_for_status()
                # 获取二进制响应
                response_bytes = await response.read()
                
                # 使用GB2312解码
                encoding = self.config.get("encoding", "utf-8")
                try:
                    decoded_content = response_bytes.decode(encoding)
                except UnicodeDecodeError:
                    logger.warning(f"Failed to decode with {encoding}, falling back to utf-8")
                    decoded_content = response_bytes.decode("utf-8", errors="replace")
                
                return decoded_content
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
                    # 移除日期中的多余空格
                    date_text = re.sub(r'\s+', ' ', date_text)
                    
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
                        # 早报的日期格式可能为：2025-03-15- 20:25:27 或 2025-03-15 20:25:27
                        formats_to_try = [
                            "%Y-%m-%d- %H:%M:%S",
                            "%Y-%m-%d %H:%M:%S",
                            "%Y-%m-%d- %H:%M",
                            "%Y-%m-%d %H:%M"
                        ]
                        
                        for fmt in formats_to_try:
                            try:
                                published_at = datetime.datetime.strptime(date_text, fmt)
                                break
                            except ValueError:
                                continue
                                
                        if not published_at:
                            raise ValueError(f"Could not parse date with any format: {date_text}")
                            
                    except Exception as e:
                        logger.error(f"Error parsing date {date_text}: {str(e)}")
                        
                        # 尝试其他可能的日期格式
                        try:
                            # 尝试解析相对日期
                            now = datetime.datetime.now()
                            if ":" in date_text:  # 包含时间
                                if "-" in date_text:  # 包含日期
                                    # 尝试不同的日期格式，包括可能有连字符的格式
                                    for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d- %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m-%d %H:%M"]:
                                        try:
                                            if fmt == "%m-%d %H:%M":
                                                dt = datetime.datetime.strptime(date_text.strip(), fmt)
                                                published_at = dt.replace(year=now.year)
                                            else:
                                                published_at = datetime.datetime.strptime(date_text.strip(), fmt)
                                            break
                                        except:
                                            continue
                        except Exception as e2:
                            logger.error(f"Error parsing alternative date format {date_text}: {str(e2)}")
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,  # 早报的移动版URL与PC版相同
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=published_at,
                        extra={"is_top": False, "mobile_url": url, 
                            
                            
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