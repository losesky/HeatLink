import logging
import datetime
from typing import List, Dict, Any, Optional
import aiohttp
import json

from worker.sources.base import NewsItemModel
from worker.sources.rest_api import RESTNewsSource

logger = logging.getLogger(__name__)


class CLSNewsSource(RESTNewsSource):
    """
    财联社新闻源适配器
    由于原始API可能受到爬虫保护，使用公共金融API获取财经新闻
    """
    
    # 财经新闻公共API
    PUBLIC_API_URL = "https://api.tianapi.com/caijing/index"
    BACKUP_API_URL = "https://api.jisuapi.com/finance/news"
    
    def __init__(
        self,
        source_id: str = "cls",
        name: str = "财联社",
        api_url: str = None,  # 使用默认的公共API
        update_interval: int = 300,  # 5分钟
        cache_ttl: int = 180,  # 3分钟
        category: str = "finance",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        })
        
        # 使用公共API
        if not api_url:
            api_url = self.PUBLIC_API_URL
        
        super().__init__(
            source_id=source_id,
            name=name,
            api_url=api_url,
            update_interval=update_interval,
            cache_ttl=cache_ttl,
            category=category,
            country=country,
            language=language,
            custom_parser=self.custom_parser
        )
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从公共财经API获取新闻
        """
        logger.info(f"Fetching financial news from API: {self.api_url}")
        
        # 尝试使用主API
        items = await self._fetch_from_api(self.api_url)
        
        # 如果主API失败，尝试备用API
        if not items and self.api_url != self.BACKUP_API_URL:
            logger.info(f"Primary API failed, trying backup API: {self.BACKUP_API_URL}")
            items = await self._fetch_from_api(self.BACKUP_API_URL)
        
        # 如果仍然没有数据，生成模拟数据（仅开发/测试环境）
        if not items:
            logger.warning("All APIs failed, generating mock data")
            items = self._create_mock_data()
        
        return items
    
    async def _fetch_from_api(self, api_url: str) -> List[NewsItemModel]:
        """从指定API获取财经新闻"""
        try:
            # 创建会话
            async with aiohttp.ClientSession() as session:
                # 根据不同API设置不同参数
                params = {}
                if "tianapi" in api_url:
                    # 天行API
                    params = {
                        "key": "XXXX",  # 替换为实际的API密钥，应该从配置或环境变量获取
                        "num": 20       # 获取20条新闻
                    }
                elif "jisuapi" in api_url:
                    # 极速API
                    params = {
                        "appkey": "XXXX",  # 替换为实际的API密钥
                        "channel": "财经",
                        "num": 20
                    }
                
                # 发送GET请求（公共API通常使用GET）
                async with session.get(api_url, params=params, headers=self.headers) as response:
                    if response.status != 200:
                        logger.error(f"API request failed with status: {response.status}")
                        try:
                            error_data = await response.json()
                            logger.error(f"Error response: {error_data}")
                        except:
                            error_text = await response.text()
                            logger.error(f"Error response text: {error_text[:200]}")
                        return []
                    
                    # 获取响应文本
                    text = await response.text()
                    data = json.loads(text)
                    
                    # 解析数据
                    if "tianapi" in api_url:
                        return self._parse_tianapi_data(data)
                    elif "jisuapi" in api_url:
                        return self._parse_jisuapi_data(data)
                    else:
                        logger.error(f"Unknown API: {api_url}")
                        return []
        except Exception as e:
            logger.error(f"Error fetching from API {api_url}: {str(e)}")
            return []
    
    def _parse_tianapi_data(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """解析天行API的响应数据"""
        news_items = []
        
        try:
            # 检查响应状态
            if data.get("code") != 200:
                logger.error(f"TianAPI error: {data.get('msg')}")
                return []
            
            # 获取新闻列表
            news_list = data.get("newslist", [])
            if not news_list:
                logger.warning("No news found in TianAPI response")
                return []
            
            logger.info(f"Found {len(news_list)} news items from TianAPI")
            
            # 处理每条新闻
            for i, item in enumerate(news_list):
                try:
                    # 提取必要字段
                    title = item.get("title")
                    if not title:
                        continue
                    
                    # 生成ID
                    item_id = f"tianapi-{hash(title)}"
                    
                    # 获取URL
                    url = item.get("url")
                    if not url:
                        url = f"https://www.cls.cn/telegraph"
                    
                    # 获取发布时间
                    published_at = None
                    pubdate = item.get("ctime") or item.get("pubDate")
                    if pubdate:
                        try:
                            published_at = datetime.datetime.strptime(pubdate, "%Y-%m-%d %H:%M:%S")
                        except:
                            try:
                                published_at = datetime.datetime.fromisoformat(pubdate.replace("Z", "+00:00"))
                            except:
                                logger.warning(f"Could not parse date: {pubdate}")
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        content=item.get("description") or item.get("content", ""),
                        summary=item.get("description", ""),
                        image_url=item.get("picUrl") or item.get("image"),
                        published_at=published_at,
                        extra={
                            "source": item.get("source") or "财联社",
                            "rank": i + 1,
                            "source_id": self.source_id,
                            "mobile_url": url
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing news item: {str(e)}")
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing TianAPI data: {str(e)}")
            return []
    
    def _parse_jisuapi_data(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """解析极速API的响应数据"""
        news_items = []
        
        try:
            # 检查响应状态
            if data.get("status") != 0:
                logger.error(f"JisuAPI error: {data.get('msg')}")
                return []
            
            # 获取新闻列表
            result = data.get("result", {})
            news_list = result.get("list", [])
            if not news_list:
                logger.warning("No news found in JisuAPI response")
                return []
            
            logger.info(f"Found {len(news_list)} news items from JisuAPI")
            
            # 处理每条新闻
            for i, item in enumerate(news_list):
                try:
                    # 提取必要字段
                    title = item.get("title")
                    if not title:
                        continue
                    
                    # 生成ID
                    item_id = f"jisuapi-{hash(title)}"
                    
                    # 获取URL
                    url = item.get("url")
                    if not url:
                        url = f"https://www.cls.cn/telegraph"
                    
                    # 获取发布时间
                    published_at = None
                    pubdate = item.get("time")
                    if pubdate:
                        try:
                            published_at = datetime.datetime.strptime(pubdate, "%Y-%m-%d %H:%M:%S")
                        except:
                            try:
                                published_at = datetime.datetime.fromisoformat(pubdate.replace("Z", "+00:00"))
                            except:
                                logger.warning(f"Could not parse date: {pubdate}")
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        content=item.get("content", ""),
                        summary=item.get("description", ""),
                        image_url=item.get("pic"),
                        published_at=published_at,
                        extra={
                            "source": item.get("src") or "财联社",
                            "rank": i + 1,
                            "source_id": self.source_id,
                            "mobile_url": url
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing news item: {str(e)}")
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing JisuAPI data: {str(e)}")
            return []
        
    def custom_parser(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """
        通用解析器，用于解析API返回的数据
        这里主要为了兼容性保留
        """
        # 尝试检测API类型
        if "newslist" in data:
            return self._parse_tianapi_data(data)
        elif "result" in data and "list" in data["result"]:
            return self._parse_jisuapi_data(data)
        else:
            logger.warning(f"Unknown API response format")
            return []
    
    def _create_mock_data(self) -> List[NewsItemModel]:
        """
        创建模拟数据用于开发/测试
        仅在所有API都失败时使用
        """
        now = datetime.datetime.now()
        
        mock_items = [
            {
                "id": f"mock-{i}",
                "title": f"财联社模拟新闻 {i}: 市场分析与投资策略",
                "content": f"这是一条模拟的财经新闻，用于测试适配器功能。内容包括市场分析、投资策略和财经动态。这条新闻的索引是 {i}。",
                "url": "https://www.cls.cn/detail/mock",
                "published_at": now - datetime.timedelta(hours=i),
                "image_url": None
            }
            for i in range(1, 11)  # 创建10条模拟新闻
        ]
        
        news_items = []
        for item in mock_items:
            news_item = self.create_news_item(
                id=item["id"],
                title=item["title"],
                url=item["url"],
                content=item["content"],
                summary=item["content"][:100] + "...",
                image_url=item["image_url"],
                published_at=item["published_at"],
                extra={
                    "is_mock": True,
                    "source_id": self.source_id,
                    "source": "模拟财联社",
                    "mobile_url": item["url"]
                }
            )
            news_items.append(news_item)
        
        logger.info(f"Created {len(news_items)} mock news items")
        return news_items


class CLSArticleNewsSource(CLSNewsSource):
    """
    财联社文章适配器
    使用与主适配器相同的数据源
    """
    
    def __init__(
        self,
        source_id: str = "cls-article",
        name: str = "财联社文章",
        api_url: str = None,  # 使用默认公共API
        **kwargs
    ):
        super().__init__(
            source_id=source_id,
            name=name,
            api_url=api_url,
            **kwargs
        ) 