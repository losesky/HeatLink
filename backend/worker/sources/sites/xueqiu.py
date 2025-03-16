import logging
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource
from worker.utils.http_client import http_client

logger = logging.getLogger(__name__)


class XueqiuHotStockSource(APINewsSource):
    """
    雪球热门股票适配器
    """
    
    def __init__(
        self,
        source_id: str = "xueqiu",
        name: str = "雪球热门股票",
        api_url: str = "https://stock.xueqiu.com/v5/stock/hot_stock/list.json?size=30&_type=10&type=10",
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
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://xueqiu.com/",
                "Accept": "application/json, text/plain, */*"
            }
        })
        
        super().__init__(
            source_id=source_id,
            name=name,
            api_url=api_url,
            update_interval=update_interval,
            cache_ttl=cache_ttl,
            category=category,
            country=country,
            language=language,
            config=config
        )
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从雪球获取热门股票
        需要先获取cookie
        """
        try:
            client = await self.http_client
            # 先访问雪球首页获取cookie
            async with client.get(
                url="https://xueqiu.com/hq",
                headers=self.headers
            ) as cookie_response:
                # 从响应头中提取cookie
                if hasattr(cookie_response, "cookies"):
                    cookies = cookie_response.cookies
                    cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
                    self.headers["Cookie"] = cookie_str
            
            # 获取热门股票数据
            async with client.get(
                url=self.api_url,
                headers=self.headers
            ) as response:
                response_json = await response.json()
                # 解析响应
                return await self.parse_response(response_json)
            
        except Exception as e:
            logger.error(f"Error fetching Xueqiu hot stocks: {str(e)}")
            raise
    
    async def parse_response(self, response: Any) -> List[NewsItemModel]:
        """
        解析雪球热门股票API响应
        """
        try:
            news_items = []
            
            items = response.get("data", {}).get("items", [])
            for item in items:
                try:
                    # 跳过广告
                    if item.get("ad", 0) == 1:
                        continue
                    
                    # 获取股票代码
                    code = item.get("code", "")
                    if not code:
                        continue
                    
                    # 生成唯一ID
                    item_id = self.generate_id(code)
                    
                    # 获取股票名称
                    name = item.get("name", "")
                    if not name:
                        continue
                    
                    # 获取URL
                    url = f"https://xueqiu.com/s/{code}"
                    
                    # 获取涨跌幅
                    percent = item.get("percent", 0)
                    
                    # 获取交易所
                    exchange = item.get("exchange", "")
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=item_id,
                        title=name,
                        url=url,  # 雪球的移动版URL与PC版相同
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=None,
                        extra={"is_top": False, "mobile_url": url, 
                            "source_id": self.source_id,
                            "source_name": self.name,
                            "code": code,
                            "percent": percent,
                            "exchange": exchange
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing Xueqiu hot stock item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing Xueqiu hot stock response: {str(e)}")
            return [] 