import logging
import asyncio
import json
from typing import List, Dict, Any, Optional
import datetime

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource
from worker.utils.http_client import http_client

logger = logging.getLogger(__name__)


class DouyinHotNewsSource(APINewsSource):
    """
    抖音热搜适配器
    使用抖音官方API获取热搜榜单，并提供第三方API作为备选方案
    """
    
    # 第三方API URL
    THIRD_PARTY_API_URL = "https://api.vvhan.com/api/hotlist/douyin"
    
    def __init__(
        self,
        source_id: str = "douyin",
        name: str = "抖音热搜",
        api_url: str = "https://www.douyin.com/aweme/v1/web/hot/search/list/?device_platform=webapp&aid=6383&channel=channel_pc_web&detail_list=1",
        update_interval: int = 600,  # 10分钟
        cache_ttl: int = 300,  # 5分钟
        category: str = "social",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://www.douyin.com/",
                "Accept": "application/json, text/plain, */*"
            },
            # 添加第三方API URL和其他配置参数
            "third_party_api_url": self.THIRD_PARTY_API_URL,
            "use_third_party_api": True,
            "max_retries": 3,
            "retry_delay": 2,
            "request_timeout": 10  # 10秒超时
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
        从抖音获取热搜，增加重试逻辑和备选API方案
        """
        logger.info("Fetching Douyin hot search")
        
        try:
            # 获取配置参数
            max_retries = self.config.get("max_retries", 3)
            retry_delay = self.config.get("retry_delay", 2)
            timeout = self.config.get("request_timeout", 10)
            
            # 尝试从官方API获取数据
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(f"Attempting to fetch from official API (attempt {attempt}/{max_retries})")
                    items = await self._fetch_from_official_api(timeout)
                    if items:
                        logger.info(f"Successfully fetched {len(items)} items from official API")
                        return items
                except Exception as e:
                    error_message = str(e)
                    logger.error(f"Error fetching from official API (attempt {attempt}/{max_retries}): {error_message}")
                    
                    # 最后一次尝试失败，尝试备选API
                    if attempt >= max_retries:
                        logger.info("All attempts with official API failed, will try third-party API as fallback")
                        break
                    
                    # 计算重试延迟（使用指数退避策略）
                    current_delay = retry_delay * (1.5 ** (attempt - 1))
                    logger.info(f"Retrying in {current_delay:.2f} seconds...")
                    await asyncio.sleep(current_delay)
            
            # 如果官方API失败，尝试使用第三方API
            if self.config.get("use_third_party_api", True):
                try:
                    logger.info("Attempting to fetch from third-party API")
                    items = await self._fetch_from_third_party_api(timeout)
                    if items:
                        logger.info(f"Successfully fetched {len(items)} items from third-party API")
                        return items
                    logger.error("Failed to fetch data from third-party API")
                except Exception as e:
                    logger.error(f"Error fetching from third-party API: {str(e)}")
            
            logger.error("All methods failed to fetch Douyin hot search")
            return []
            
        except Exception as e:
            logger.error(f"Unexpected error during fetch: {str(e)}", exc_info=True)
            return []
    
    async def _fetch_from_official_api(self, timeout: int) -> List[NewsItemModel]:
        """
        从官方API获取抖音热搜数据
        """
        # 使用http_client单例而不是创建新的会话，避免资源泄露
        try:
            # 先访问抖音首页获取cookie
            logger.info("Fetching homepage to get cookies")
            cookie_response = await http_client.fetch(
                url="https://www.douyin.com/",
                method="GET",
                headers=self.headers,
                response_type="text",
                timeout=timeout
            )
            
            # 从响应中提取cookie的逻辑需要重新实现，因为http_client不直接返回cookies
            # 实际上，http_client会自动管理cookies，我们不需要手动提取和设置
            
            # 获取热搜数据
            logger.info(f"Fetching hot search data from: {self.api_url}")
            response = await http_client.fetch(
                url=self.api_url,
                method="GET",
                headers=self.headers,
                response_type="json",
                timeout=timeout
            )
            
            # 解析响应
            return await self.parse_response(response)
        except Exception as e:
            logger.error(f"Error in _fetch_from_official_api: {str(e)}")
            raise
    
    async def _fetch_from_third_party_api(self, timeout: int) -> List[NewsItemModel]:
        """
        从第三方API获取抖音热搜数据
        """
        try:
            api_url = self.config.get("third_party_api_url", self.THIRD_PARTY_API_URL)
            logger.info(f"Fetching hot search from third-party API: {api_url}")
            
            # 从http_client获取数据
            data = await http_client.fetch(
                url=api_url,
                method="GET",
                headers=self.headers,
                timeout=timeout,
                response_type="json"
            )
            
            if not data:
                logger.error("Empty response from third-party API")
                return []
            
            # vvhan API返回格式为{"success":true,"data":[{"title":"标题","desc":"描述","hot":"热度值"},...]}
            if "success" in data and data.get("success") is True and "data" in data:
                hot_data = data.get("data", [])
                
                if not hot_data:
                    logger.error("No hot search data found in API response")
                    return []
                
                logger.info(f"Found {len(hot_data)} items in third-party API response")
                
                # 处理提取到的数据
                items = []
                for index, item_data in enumerate(hot_data):
                    try:
                        # 提取标题
                        title = item_data.get('title', '')
                        if not title:
                            logger.warning(f"Missing title in item {index}")
                            continue
                        
                        # 生成唯一ID
                        item_id = self.generate_id(f"douyin:{title}")
                        
                        # 获取URL - 第三方API通常直接提供URL
                        url = item_data.get('url', '')
                        if not url:
                            # 如果没有URL，创建一个通用的热搜URL
                            url = f"https://www.douyin.com/search/{title}"
                        
                        # 获取热度值
                        hot_value = item_data.get('hot', '') or item_data.get('hotValue', '')
                        
                        # 创建新闻项
                        news_item = self.create_news_item(
                            id=item_id,
                            title=title,
                            url=url,
                            content=None,
                            summary=None,
                            image_url=None,
                            published_at=datetime.datetime.now(datetime.timezone.utc),
                            extra={
                                "is_top": False, 
                                "mobile_url": url, 
                                "hot_value": hot_value,
                                "rank": index + 1,
                                "source_from": "third_party_api"
                            }
                        )
                        
                        items.append(news_item)
                    except Exception as e:
                        logger.error(f"Error processing third-party API item at index {index}: {str(e)}")
                
                return items
            else:
                logger.error(f"Unexpected API response format: {data}")
                return []
        
        except Exception as e:
            logger.error(f"Error fetching from third-party API: {str(e)}")
            return []
    
    async def parse_response(self, response: Any) -> List[NewsItemModel]:
        """
        解析抖音热搜API响应
        """
        try:
            news_items = []
            
            word_list = response.get("data", {}).get("word_list", [])
            if not word_list:
                logger.warning("No word_list found in API response")
                return []
                
            logger.info(f"Found {len(word_list)} items in hot search API response")
            
            for index, item in enumerate(word_list):
                try:
                    # 生成唯一ID
                    sentence_id = item.get("sentence_id", "")
                    if not sentence_id:
                        sentence_id = self.generate_id(f"douyin:{item.get('word', '')}")
                    
                    item_id = self.generate_id(sentence_id)
                    
                    # 获取标题
                    title = item.get("word", "")
                    if not title:
                        continue
                    
                    # 获取URL
                    url = f"https://www.douyin.com/hot/{sentence_id}"
                    
                    # 获取热度值
                    hot_value = item.get("hot_value", "")
                    
                    # 获取发布时间
                    event_time = item.get("event_time", "")
                    published_at = self.parse_date(event_time) if event_time else datetime.datetime.now(datetime.timezone.utc)
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        content=None,
                        summary=None,
                        image_url=None,
                        published_at=published_at,
                        extra={
                            "is_top": False, 
                            "mobile_url": url, 
                            "hot_value": hot_value,
                            "rank": index + 1,
                            "source_from": "official_api"
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing Douyin hot item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing Douyin hot response: {str(e)}")
            return []
            
    def parse_date(self, timestamp: Any) -> Optional[datetime.datetime]:
        """解析时间戳为datetime对象"""
        if not timestamp:
            return None
            
        try:
            if isinstance(timestamp, str):
                timestamp = int(timestamp)
            return datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
        except Exception as e:
            logger.error(f"Error parsing timestamp {timestamp}: {str(e)}")
            return None 