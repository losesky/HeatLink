import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

from worker.sources.base import NewsItemModel
from worker.sources.web import WebNewsSource

logger = logging.getLogger(__name__)


class GitHubTrendingSource(WebNewsSource):
    """
    GitHub Trending适配器
    """
    
    def __init__(
        self,
        source_id: str = "github",
        name: str = "GitHub Trending",
        url: str = "https://github.com/trending?spoken_language_code=",
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
        解析GitHub Trending网页响应
        """
        try:
            news_items = []
            base_url = "https://github.com"
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(response, 'html.parser')
            
            # 查找仓库列表
            repo_list = soup.select("main .Box div[data-hpc] article")
            
            for item in repo_list:
                try:
                    # 获取链接和标题
                    link_element = item.select_one("h2 a")
                    if not link_element:
                        continue
                    
                    url_path = link_element.get("href", "")
                    url = f"{base_url}{url_path}"
                    
                    # 清理标题文本
                    title = link_element.text.replace("\n", "").strip()
                    
                    # 获取星标数
                    star_element = item.select_one("[href$=stargazers]")
                    star_count = star_element.text.replace("\n", "").replace(" ", "").strip() if star_element else ""
                    
                    # 获取描述
                    desc_element = item.select_one("p")
                    description = desc_element.text.replace("\n", "").strip() if desc_element else ""
                    
                    # 生成唯一ID
                    item_id = self.generate_id(url_path)
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,  # GitHub的移动版URL与PC版相同
                        content=description,
                        summary=description,
                        image_url=None,
                        published_at=None,
                        extra={"is_top": False, "mobile_url": url, 
                            
                            
                            "star_count": star_count
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing GitHub Trending item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing GitHub Trending response: {str(e)}")
            return [] 