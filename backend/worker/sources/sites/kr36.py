import logging
import datetime
import time
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
        
        # 添加初始化日志
        logger.info(f"[36KR-DEBUG] 初始化 {source_id} 适配器")
        logger.info(f"[36KR-DEBUG] 缓存相关设置: update_interval={update_interval}秒, cache_ttl={cache_ttl}秒")
        logger.info(f"[36KR-DEBUG] 缓存字段初始状态: _cached_news_items={'有' if hasattr(self, '_cached_news_items') and self._cached_news_items else '无'}")
        logger.info(f"[36KR-DEBUG] _last_cache_update={getattr(self, '_last_cache_update', 0)}")
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析36氪快讯网页响应
        """
        logger.info(f"[36KR-DEBUG] 开始解析36氪快讯网页响应，内容长度: {len(response) if response else 0}")
        logger.info(f"[36KR-DEBUG] 当前缓存状态: _cached_news_items={'有' if hasattr(self, '_cached_news_items') and self._cached_news_items else '无'}, _last_cache_update={getattr(self, '_last_cache_update', 0)}")
        
        try:
            news_items = []
            base_url = "https://www.36kr.com"
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(response, 'html.parser')
            
            # 查找快讯列表
            news_list = soup.select(".newsflash-item")
            
            logger.info(f"[36KR-DEBUG] 找到 {len(news_list)} 条快讯")
            
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
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=published_at,
                        extra={"is_top": False, "mobile_url": None, 
                            "relative_date": relative_date
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing 36Kr news item: {str(e)}")
                    continue
            
            logger.info(f"[36KR-DEBUG] 成功解析 {len(news_items)} 条36氪快讯")
            return news_items
        except Exception as e:
            logger.error(f"Error parsing 36Kr response: {str(e)}")
            logger.info(f"[36KR-DEBUG] 解析36氪快讯出错: {str(e)}")
            return []
    
    def is_cache_valid(self) -> bool:
        """
        检查缓存是否有效
        
        Returns:
            bool: 缓存是否有效
        """
        has_cached_items = bool(self._cached_news_items)
        cache_age = time.time() - self._last_cache_update if self._last_cache_update > 0 else float('inf')
        cache_ttl_valid = cache_age < self.cache_ttl
        
        logger.info(f"[36KR-DEBUG] 缓存状态检查")
        logger.info(f"[36KR-DEBUG] _cached_news_items={'有' if has_cached_items else '无'}, 条目数={len(self._cached_news_items) if self._cached_news_items else 0}")
        logger.info(f"[36KR-DEBUG] _last_cache_update={self._last_cache_update}, 缓存年龄={cache_age:.2f}秒")
        logger.info(f"[36KR-DEBUG] cache_ttl={self.cache_ttl}秒, 是否未过期={cache_ttl_valid}")
        
        cache_valid = has_cached_items and cache_ttl_valid
        logger.info(f"[36KR-DEBUG] 最终缓存有效性={cache_valid}")
        
        return cache_valid
    
    async def update_cache(self, news_items: List[NewsItemModel]) -> None:
        """
        更新缓存
        
        Args:
            news_items: 新闻项列表
        """
        logger.info(f"[36KR-DEBUG] 开始更新缓存，新闻条目数={len(news_items) if news_items else 0}")
        logger.info(f"[36KR-DEBUG] 缓存前状态: _cached_news_items条目数={len(self._cached_news_items) if self._cached_news_items else 0}, _last_cache_update={self._last_cache_update}")
        
        # 如果news_items为空且已有缓存，保留现有缓存
        if not news_items and self._cached_news_items:
            logger.info(f"[36KR-DEBUG] 新闻条目为空，保留现有缓存，不更新")
            return
            
        self._cached_news_items = news_items
        self._last_cache_update = time.time()
            
        logger.info(f"[36KR-DEBUG] 缓存已更新，新状态: _cached_news_items条目数={len(self._cached_news_items) if self._cached_news_items else 0}, _last_cache_update={self._last_cache_update}")
        
    async def fetch(self) -> List[NewsItemModel]:
        """
        从网页抓取新闻
        
        Returns:
            List[NewsItemModel]: 新闻列表
        """
        logger.info(f"[36KR-DEBUG] 开始获取36氪快讯数据")
        try:
            # 获取网页内容
            content = await self.fetch_content()
            if not content:
                logger.warning(f"[36KR-DEBUG] 获取网页内容失败")
                return []
            
            # 解析响应
            news_items = await self.parse_response(content)
            logger.info(f"[36KR-DEBUG] 成功获取 {len(news_items)} 条36氪快讯")
            return news_items
        
        except Exception as e:
            logger.error(f"[36KR-DEBUG] 获取36氪快讯出错: {str(e)}")
            return []
    
    async def clear_cache(self) -> None:
        """
        清除缓存
        """
        old_count = len(self._cached_news_items) if hasattr(self, '_cached_news_items') and self._cached_news_items else 0
        
        logger.info(f"[36KR-DEBUG] 开始清除缓存，当前缓存条目数={old_count}")
        
        self._cached_news_items = []
        self._last_cache_update = 0
        
        logger.info(f"[36KR-DEBUG] 缓存已清除，旧缓存条目数={old_count}") 