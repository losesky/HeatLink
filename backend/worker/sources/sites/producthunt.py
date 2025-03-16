import logging
from typing import List, Dict, Any, Optional

from bs4 import BeautifulSoup

from worker.sources.base import NewsItemModel
from worker.sources.web import WebNewsSource

logger = logging.getLogger(__name__)


class ProductHuntNewsSource(WebNewsSource):
    """
    Product Hunt新闻源适配器
    """
    
    def __init__(
        self,
        source_id: str = "producthunt",
        name: str = "Product Hunt",
        url: str = "https://www.producthunt.com/",
        update_interval: int = 3600,  # 1小时
        cache_ttl: int = 1800,  # 30分钟
        category: str = "technology",
        country: str = "US",
        language: str = "en",
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
        解析Product Hunt网页响应
        """
        try:
            news_items = []
            base_url = "https://www.producthunt.com"
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(response, 'html.parser')
            
            # 查找产品列表
            # Product Hunt使用data-test属性来标识元素
            product_list = soup.select('[data-test="homepage-section-0"] [data-test^="post-item"]')
            
            for item in product_list:
                try:
                    # 获取链接
                    link_element = item.select_one("a")
                    if not link_element:
                        continue
                    
                    url_path = link_element.get("href", "")
                    
                    # 获取标题
                    title_element = item.select_one('a[data-test^="post-name"]')
                    if not title_element:
                        continue
                    title = title_element.text.strip()
                    
                    # 获取ID
                    item_id_attr = item.get("data-test", "")
                    if not item_id_attr:
                        continue
                    
                    item_id = item_id_attr.replace("post-item-", "")
                    
                    # 获取投票数
                    vote_element = item.select_one('[data-test="vote-button"]')
                    vote_count = vote_element.text.strip() if vote_element else ""
                    
                    if not url_path or not title or not item_id:
                        continue
                    
                    # 生成完整URL
                    url = f"{base_url}{url_path}"
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,  # Product Hunt的移动版URL与PC版相同
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=None,  # Product Hunt没有提供发布时间
                        extra={
                            "is_top": False,
                            "mobile_url": url, 
                            
                            
                            "vote_count": vote_count,
                            "info": f"△︎ {vote_count}" if vote_count else ""
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing Product Hunt item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing Product Hunt response: {str(e)}")
            return [] 