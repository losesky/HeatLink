import logging
import hashlib
import datetime
import random
from typing import List, Dict, Any, Optional
import asyncio
import json
import urllib.parse

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource
from worker.utils.http_client import http_client, HTTPClient

logger = logging.getLogger(__name__)

# 定义常用的用户代理字符串列表，随机选择以避免被屏蔽
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/96.0.4664.53 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Mobile Safari/537.36"
]

class ToutiaoHotNewsSource(APINewsSource):
    """
    今日头条热搜适配器
    注意：原始API可能已经更改，目前使用第三方API作为备选方案
    增强了稳定性，包括多种备用获取方式和更强大的重试机制
    """
    
    # 第三方API URLs - 已更新为最新可用的API
    THIRD_PARTY_API_URLS = [
        "https://api.vvhan.com/api/hotlist/jrtt",
        "https://api.oioweb.cn/api/common/HotList",
        "https://api.qqsuu.cn/api/all/hotlist",
        "https://api.mcloc.cn/toutiao"
    ]
    
    def __init__(
        self,
        source_id: str = "toutiao",
        name: str = "今日头条热搜",
        api_url: str = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
        update_interval: int = 600,  # 10分钟
        cache_ttl: int = 300,  # 5分钟
        category: str = "news",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        # 随机选择一个用户代理
        user_agent = random.choice(USER_AGENTS)
        
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": user_agent,
                "Referer": "https://www.toutiao.com/",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Origin": "https://www.toutiao.com",
                "Connection": "keep-alive"
            },
            # 添加第三方API URLs
            "third_party_api_urls": self.THIRD_PARTY_API_URLS,
            "use_third_party_api": True,
            "max_retries": 3,
            "retry_delay": 2,
            "timeout": 10
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
        获取头条热榜数据，增强了错误处理和重试机制
        """
        logger.info("Fetching Toutiao hot news")
        
        try:
            # 从配置获取参数
            max_retries = self.config.get("max_retries", 3)
            base_delay = self.config.get("retry_delay", 2)
            timeout = self.config.get("timeout", 10)
            
            # 尝试从原始API获取数据
            logger.info("Attempting to fetch from original API")
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(f"Fetching from original API: {self.api_url} (attempt {attempt}/{max_retries})")
                    items = await self._fetch_from_original_api(timeout)
                    if items:
                        logger.info(f"Successfully fetched {len(items)} items from original API")
                        return items
                    logger.warning("Original API returned 0 items")
                except Exception as e:
                    error_message = str(e)
                    logger.warning(f"Error fetching from original API (attempt {attempt}/{max_retries}): {error_message}")
                    
                    # 最后一次尝试失败，不再重试
                    if attempt >= max_retries:
                        logger.info("All attempts with original API failed, will try third-party APIs as fallback")
                        break
                    
                    # 计算重试延迟（指数退避策略）
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
            
            # 如果原始API失败，尝试使用第三方API
            third_party_urls = self.config.get("third_party_api_urls", self.THIRD_PARTY_API_URLS)
            logger.info(f"Attempting to fetch from {len(third_party_urls)} third-party APIs")
            
            for api_url in third_party_urls:
                try:
                    logger.info(f"Fetching from third-party API: {api_url}")
                    items = await self._fetch_from_third_party_api(api_url, timeout)
                    if items:
                        logger.info(f"Successfully fetched {len(items)} items from third-party API: {api_url}")
                        return items
                    logger.warning(f"Third-party API {api_url} returned 0 items")
                except Exception as e:
                    logger.warning(f"Error fetching from third-party API {api_url}: {str(e)}")
            
            # 如果所有API都失败，抛出异常
            logger.error("All APIs failed, unable to fetch Toutiao hot news")
            raise RuntimeError("无法获取今日头条热搜数据：所有API请求均失败")
            
        except Exception as e:
            logger.error(f"Unexpected error during fetch: {str(e)}", exc_info=True)
            # 不再返回空列表，而是重新抛出异常
            raise
    
    async def _fetch_from_original_api(self, timeout: int) -> List[NewsItemModel]:
        """
        从原始API获取头条热搜数据
        """
        try:
            # 获取API响应
            response = await http_client.fetch(
                url=self.api_url,
                method="GET",
                headers=self.headers,
                params=self.params,
                json_data=self.json_data,
                response_type=self.response_type,
                timeout=timeout
            )
            
            # 解析响应
            return await self.parse_response(response)
        except Exception as e:
            # 将异常重新抛出，让调用者处理
            raise e
    
    async def _fetch_from_third_party_api(self, api_url: str, timeout: int):
        """
        从第三方API获取头条热搜数据
        """
        try:
            # 设置请求头，不同API可能需要不同的请求头
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.toutiao.com/"
            }
            
            logger.info(f"Fetching hot news from third-party API: {api_url}")
            
            # 从异步HTTP客户端获取数据
            data = await http_client.fetch(
                url=api_url,
                method="GET",
                headers=headers,
                timeout=timeout,
            )
            
            if not data:
                logger.error("Empty response from third-party API")
                return []
            
            # 检查API响应结构
            # 尝试解析为JSON (如果还不是json对象)
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON from third-party API: {e}")
                    return []
            
            # vvhan API格式
            if api_url.startswith("https://api.vvhan.com"):
                return self._parse_vvhan_api_response(data)
            # 其他通用格式
            else:
                return self._parse_generic_api_response(data, api_url)
        
        except Exception as e:
            logger.error(f"Error fetching from third-party API {api_url}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            # 不再返回空列表，而是重新抛出异常
            raise RuntimeError(f"第三方API {api_url} 请求失败: {str(e)}")
    
    def _parse_vvhan_api_response(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """解析vvhan API的响应"""
        if "success" in data and data.get("success") is True and "data" in data:
            hot_news_data = data.get("data", [])
            
            if not hot_news_data:
                logger.error("No hot news data found in vvhan API response")
                return []
            
            logger.info(f"Found {len(hot_news_data)} items in vvhan API response")
            
            # 处理提取到的数据
            items = []
            for index, item_data in enumerate(hot_news_data):
                try:
                    # 提取标题和URL
                    title = item_data.get('title', '')
                    url = item_data.get('url', '')
                    
                    if not title:
                        logger.warning(f"Missing title in vvhan API item {index}")
                        continue
                    
                    # 如果缺少URL，则创建搜索URL
                    if not url:
                        url = f"https://www.toutiao.com/search/?keyword={urllib.parse.quote(title)}"
                    
                    # 生成唯一ID
                    news_id = hashlib.md5(f"{url}_{title}".encode()).hexdigest()
                    
                    # 获取排名
                    rank = index + 1
                    
                    # 获取热度（如果有）
                    hot_value = item_data.get('hot', '') or item_data.get('hotValue', '')
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=news_id,
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
                            "rank": rank,
                            "source_from": "vvhan_api"
                        }
                    )
                    
                    items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing vvhan API item at index {index}: {str(e)}")
            
            return items
        else:
            logger.error(f"Unexpected vvhan API response format: {data}")
            return []
    
    def _parse_generic_api_response(self, data: Dict[str, Any], api_url: str) -> List[NewsItemModel]:
        """解析通用API的响应"""
        items = []
        
        try:
            # 尝试提取热搜数据，处理不同的API格式
            hot_news_data = None
            
            # 尝试各种常见的数据结构
            if "data" in data:
                hot_news_data = data["data"]
            elif "list" in data:
                hot_news_data = data["list"]
            elif "result" in data and isinstance(data["result"], list):
                hot_news_data = data["result"]
            elif "newslist" in data:
                hot_news_data = data["newslist"]
            elif isinstance(data, list):
                hot_news_data = data
                
            if not hot_news_data or not isinstance(hot_news_data, list):
                logger.error(f"Could not extract hot news data from {api_url} response")
                return []
                
            logger.info(f"Found {len(hot_news_data)} items in generic API response")
            
            # 处理提取到的数据
            for index, item_data in enumerate(hot_news_data):
                try:
                    # 尝试各种可能的字段名提取标题
                    title = None
                    for key in ['title', 'name', 'text', 'content', 'headline']:
                        if key in item_data and item_data[key]:
                            title = item_data[key]
                            break
                    
                    if not title:
                        logger.warning(f"Missing title in generic API item {index}")
                        continue
                    
                    # 尝试提取URL
                    url = None
                    for key in ['url', 'link', 'href', 'target']:
                        if key in item_data and item_data[key]:
                            url = item_data[key]
                            break
                    
                    # 如果缺少URL，则创建搜索URL
                    if not url:
                        url = f"https://www.toutiao.com/search/?keyword={urllib.parse.quote(title)}"
                    
                    # 生成唯一ID
                    news_id = hashlib.md5(f"{url}_{title}".encode()).hexdigest()
                    
                    # 获取排名
                    rank = index + 1
                    
                    # 尝试提取热度值
                    hot_value = None
                    for key in ['hot', 'hotValue', 'heat', 'score', 'views', 'popularity']:
                        if key in item_data and item_data[key]:
                            hot_value = item_data[key]
                            break
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=news_id,
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
                            "rank": rank,
                            "source_from": f"third_party_{api_url.split('//')[1].split('/')[0]}"
                        }
                    )
                    
                    items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing generic API item at index {index}: {str(e)}")
            
            return items
        except Exception as e:
            logger.error(f"Error parsing generic API response from {api_url}: {str(e)}")
            return []
    
    def _create_mock_data(self) -> List[NewsItemModel]:
        """
        创建模拟数据，作为最后的备用方案
        当所有API都失败时使用
        """
        mock_hot_topics = [
            {"title": "国家发改委发布重要经济政策", "hot": "3254896"},
            {"title": "外交部回应国际热点问题", "hot": "2987451"},
            {"title": "新冠疫情最新防控措施公布", "hot": "2876543"},
            {"title": "教育部公布新的教育改革方案", "hot": "2765432"},
            {"title": "中国航天取得重大突破", "hot": "2654321"},
            {"title": "人工智能技术最新发展", "hot": "2543210"},
            {"title": "全国房地产市场最新分析", "hot": "2432109"},
            {"title": "环保部门发布空气质量报告", "hot": "2321098"},
            {"title": "重大体育赛事最新战况", "hot": "2210987"},
            {"title": "全国交通运输发展新规划", "hot": "2109876"},
            {"title": "医疗健康领域最新研究成果", "hot": "2098765"},
            {"title": "国家能源局发布新能源政策", "hot": "1987654"},
            {"title": "金融市场监管新措施", "hot": "1876543"},
            {"title": "农业农村部推进乡村振兴", "hot": "1765432"},
            {"title": "文化和旅游业复苏新举措", "hot": "1654321"}
        ]
        
        now = datetime.datetime.now(datetime.timezone.utc)
        
        news_items = []
        for index, topic in enumerate(mock_hot_topics):
            try:
                title = topic["title"]
                url = f"https://www.toutiao.com/search/?keyword={urllib.parse.quote(title)}"
                
                # 生成唯一ID
                news_id = hashlib.md5(f"mock_{url}_{title}".encode()).hexdigest()
                
                news_item = self.create_news_item(
                    id=news_id,
                    title=title,
                    url=url,
                    content=None,
                    summary=None,
                    image_url=None,
                    published_at=now,
                    extra={
                        "is_top": False,
                        "mobile_url": url,
                        "hot_value": topic["hot"],
                        "rank": index + 1,
                        "source_from": "mock_data",
                        "is_mock": True
                    }
                )
                
                news_items.append(news_item)
            except Exception as e:
                logger.error(f"Error creating mock data item: {str(e)}")
        
        return news_items
    
    async def parse_response(self, response: Any) -> List[NewsItemModel]:
        """
        解析今日头条热搜API响应
        """
        try:
            news_items = []
            
            # 检查response是否为字典类型
            if not isinstance(response, dict):
                logger.error(f"Unexpected response type: {type(response)}")
                return []
                
            # 检查response是否包含data字段
            if "data" not in response:
                logger.error("Response does not contain 'data' field")
                return []
                
            # 检查data是否为列表类型
            data_list = response.get("data", [])
            if not isinstance(data_list, list):
                logger.error(f"Unexpected data type: {type(data_list)}")
                return []
                
            logger.info(f"Processing {len(data_list)} items from original API response")
            
            for item in data_list:
                try:
                    # 生成唯一ID
                    cluster_id = item.get("ClusterIdStr", "")
                    if not cluster_id:
                        logger.warning("Missing ClusterIdStr in item")
                        continue
                        
                    item_id = self.generate_id(cluster_id)
                    
                    # 获取标题
                    title = item.get("Title", "")
                    if not title:
                        logger.warning("Missing Title in item")
                        continue
                    
                    # 获取URL
                    url = f"https://www.toutiao.com/trending/{cluster_id}/"
                    
                    # 获取热度值
                    hot_value = item.get("HotValue", "")
                    
                    # 获取图标
                    image_url = None
                    if item.get("LabelUri") and isinstance(item["LabelUri"], dict) and "url" in item["LabelUri"]:
                        image_url = item["LabelUri"]["url"]
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,  # 头条的移动版URL与PC版相同
                        content=None,
                        summary=None,
                        image_url=image_url,
                        published_at=None,
                        extra={
                            "is_top": False, 
                            "mobile_url": url, 
                            "hot_value": hot_value,
                            "source_from": "original_api"
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing Toutiao hot item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing Toutiao hot response: {str(e)}")
            return [] 