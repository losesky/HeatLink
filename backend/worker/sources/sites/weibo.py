import json
import logging
import datetime
import re
import time
import random
import requests
from typing import List, Dict, Any, Optional
import asyncio

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource
from worker.utils.http_client import get, fetch, cached_get

logger = logging.getLogger(__name__)


class WeiboHotNewsSource(APINewsSource):
    """
    微博热搜适配器
    """
    def __init__(
        self,
        source_id: str = "weibo",
        name: str = "微博热搜",
        api_url: str = "https://weibo.com/ajax/side/hotSearch",
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
                "Referer": "https://weibo.com/",
                "Accept": "application/json, text/plain, */*"
            },
            "data_path": "data.realtime"
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
        
        # 备用API列表
        self.backup_apis = [
            "https://api.vvhan.com/api/wbhot",
            "https://api.oioweb.cn/api/common/HotList",
            "https://api.qqsuu.cn/api/all/hotlist",
            "https://api.mcloc.cn/toutiao"
        ]
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从微博API获取热搜数据
        混合异步和同步方式，确保数据获取的可靠性
        """
        logger.info(f"Fetching news from Weibo API: {self.api_url}")
        
        try:
            # 1. 首先尝试异步获取
            try:
                logger.info("尝试使用异步API获取微博热搜")
                response = await fetch(
                    url=self.api_url,
                    method="GET",
                    headers=self.headers,
                    params=self.params,
                    json_data=self.json_data,
                    response_type=self.response_type,
                    max_retries=2,
                    retry_delay=1
                )
                
                # 解析响应
                news_items = await self.parse_response(response)
                
                if news_items:
                    logger.info(f"成功通过异步API获取到 {len(news_items)} 条微博热搜")
                    return news_items
                else:
                    logger.warning("异步API返回0条数据，尝试同步方法")
            except Exception as e:
                logger.error(f"异步获取微博热搜失败: {str(e)}")
            
            # 2. 如果异步失败，尝试同步获取
            try:
                logger.info("尝试使用同步请求获取微博热搜")
                news_items = self._sync_fetch_weibo_hot()
                
                if news_items:
                    logger.info(f"成功通过同步请求获取到 {len(news_items)} 条微博热搜")
                    return news_items
                else:
                    logger.warning("同步请求返回0条数据，尝试备用API")
            except Exception as e:
                logger.error(f"同步获取微博热搜失败: {str(e)}")
            
            # 3. 如果原始API都失败，尝试备用API
            logger.info("尝试从备用API获取微博热搜数据")
            
            for backup_api in self.backup_apis:
                try:
                    logger.info(f"尝试从备用API获取: {backup_api}")
                    # 同步请求备用API
                    response = requests.get(
                        backup_api,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                        },
                        timeout=5
                    )
                    
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            news_items = self._parse_backup_api_data(backup_api, data)
                            
                            if news_items:
                                logger.info(f"成功从备用API {backup_api} 获取到 {len(news_items)} 条微博热搜")
                                return news_items
                            else:
                                logger.warning(f"备用API {backup_api} 返回0条数据")
                        except Exception as e:
                            logger.error(f"解析备用API {backup_api} 数据失败: {str(e)}")
                    else:
                        logger.warning(f"备用API {backup_api} 返回非200状态码: {response.status_code}")
                except Exception as e:
                    logger.error(f"请求备用API {backup_api} 失败: {str(e)}")
            
            # 4. 如果所有API都失败，抛出异常
            logger.error("所有API都失败，无法获取微博热搜数据")
            raise RuntimeError("无法获取微博热搜数据：所有API请求均失败")
            
        except Exception as e:
            logger.error(f"微博热搜获取完全失败: {str(e)}")
            # 不再返回模拟数据，而是重新抛出异常，使调用方能够正确处理错误并记录统计信息
            raise
    
    def _sync_fetch_weibo_hot(self) -> List[NewsItemModel]:
        """
        使用同步方式获取微博热搜
        
        Returns:
            List[NewsItemModel]: 解析后的微博热搜新闻项列表
        """
        try:
            response = requests.get(
                self.api_url,
                headers=self.headers,
                params=self.params,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"同步获取微博热搜API返回非200状态码: {response.status_code}")
                return []
            
            # 解析响应
            data = response.json()
            
            # 从配置中获取数据路径
            data_path = self.config.get("data_path", "data.realtime")
            
            # 解析数据路径
            path_parts = data_path.split(".")
            result_data = data
            for part in path_parts:
                if isinstance(result_data, dict) and part in result_data:
                    result_data = result_data[part]
                else:
                    logger.error(f"同步获取微博热搜数据路径 '{data_path}' 未找到")
                    return []
            
            # 确保数据是列表
            if not isinstance(result_data, list):
                logger.error(f"同步获取微博热搜数据路径 '{data_path}' 不是列表")
                return []
            
            # 处理热搜列表
            news_items = []
            for index, item in enumerate(result_data):
                try:
                    # 获取标题
                    title = item.get("word", "")
                    if not title:
                        continue
                    
                    # 获取链接
                    url = item.get("url", "")
                    if not url and title:
                        # 如果没有URL但有标题，构造一个搜索URL
                        url = f"https://s.weibo.com/weibo?q={title}"
                    
                    # 获取热度
                    hot = item.get("num", "")
                    
                    # 获取排名
                    rank = str(index + 1)
                    
                    # 判断是否置顶、新上榜等
                    is_top = item.get("is_top", 0) == 1
                    is_hot = item.get("is_hot", 0) == 1
                    is_new = item.get("is_new", 0) == 1
                    
                    # 创建唯一ID
                    unique_str = f"{self.source_id}:{title}:{url}"
                    item_id = self.generate_id(unique_str)
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        published_at=datetime.datetime.now(),
                        extra={
                            "rank": rank,
                            "hot": hot,
                            "is_top": is_top,
                            "is_new": is_new,
                            "is_hot": is_hot
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"同步处理微博热搜项出错: {str(e)}")
            
            logger.info(f"同步解析了 {len(news_items)} 条微博热搜")
            return news_items
        except Exception as e:
            logger.error(f"同步获取微博热搜完全失败: {str(e)}")
            return []
    
    def _parse_backup_api_data(self, api_url: str, data: Dict[str, Any]) -> List[NewsItemModel]:
        """
        解析备用API返回的数据
        
        Args:
            api_url: 备用API URL
            data: API返回的数据
            
        Returns:
            List[NewsItemModel]: 解析后的新闻项列表
        """
        try:
            news_items = []
            
            # 不同的API有不同的数据结构
            if "api.vvhan.com" in api_url:
                # vvhan API
                if not isinstance(data, dict) or not data.get("success", False):
                    logger.error(f"Unexpected vvhan API response format: {data}")
                    return []
                    
                items = data.get("data", [])
                for index, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                        
                    title = item.get("title", "")
                    url = item.get("url", "")
                    hot = item.get("hot", "")
                    
                    if not title:
                        continue
                        
                    if not url and title:
                        url = f"https://s.weibo.com/weibo?q={title}"
                        
                    # 创建唯一ID
                    unique_str = f"{self.source_id}:{title}:{url}"
                    item_id = self.generate_id(unique_str)
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        published_at=datetime.datetime.now(),
                        extra={
                            "rank": str(index + 1),
                            "hot": hot,
                            "from_backup_api": True
                        }
                    )
                    
                    news_items.append(news_item)
                    
            elif "api.oioweb.cn" in api_url or "api.qqsuu.cn" in api_url:
                # oioweb 或 qqsuu API
                if not isinstance(data, dict) or data.get("code", 1) != 200:
                    logger.error(f"Unexpected {api_url} API response: {data}")
                    return []
                    
                result = data.get("result", {})
                items = result.get("list", [])
                
                if not isinstance(items, list):
                    logger.error(f"{api_url} API response list is not a list: {result}")
                    return []
                    
                for index, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                        
                    title = item.get("word") or item.get("title", "")
                    url = item.get("url", "")
                    hot = item.get("hot", "")
                    
                    if not title:
                        continue
                        
                    if not url and title:
                        url = f"https://s.weibo.com/weibo?q={title}"
                        
                    # 创建唯一ID
                    unique_str = f"{self.source_id}:{title}:{url}"
                    item_id = self.generate_id(unique_str)
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        published_at=datetime.datetime.now(),
                        extra={
                            "rank": str(index + 1),
                            "hot": hot,
                            "from_backup_api": True
                        }
                    )
                    
                    news_items.append(news_item)
            
            elif "api.mcloc.cn" in api_url:
                # mcloc API
                if not isinstance(data, dict):
                    logger.error(f"Unexpected {api_url} API response: {data}")
                    return []
                    
                items = data.get("data", [])
                if not isinstance(items, list):
                    logger.error(f"{api_url} API response data is not a list: {data}")
                    return []
                
                for index, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                        
                    title = item.get("title", "")
                    url = item.get("url", "")
                    
                    if not title:
                        continue
                        
                    if not url and title:
                        url = f"https://s.weibo.com/weibo?q={title}"
                        
                    # 创建唯一ID
                    unique_str = f"{self.source_id}:{title}:{url}"
                    item_id = self.generate_id(unique_str)
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        published_at=datetime.datetime.now(),
                        extra={
                            "rank": str(index + 1),
                            "from_backup_api": True
                        }
                    )
                    
                    news_items.append(news_item)
            
            return news_items
        except Exception as e:
            logger.error(f"解析备用API {api_url} 数据失败: {str(e)}")
            return []
    
    def _generate_mock_data(self) -> List[NewsItemModel]:
        """
        生成模拟数据，当所有API获取都失败时使用
        """
        mock_data = [
            {"title": "微博服务器崩了", "rank": "1", "hot": "9999万"},
            {"title": "双汇火腿肠被曝光", "rank": "2", "hot": "8888万"},
            {"title": "诺贝尔和平奖得主揭晓", "rank": "3", "hot": "7777万"},
            {"title": "iPhone 16发布会", "rank": "4", "hot": "6666万"},
            {"title": "全国多地暴雨预警", "rank": "5", "hot": "5555万"},
            {"title": "国庆假期旅游热点", "rank": "6", "hot": "4444万"},
            {"title": "新冠疫情最新情况", "rank": "7", "hot": "3333万"},
            {"title": "A股市场行情", "rank": "8", "hot": "2222万"},
            {"title": "明星离婚风波", "rank": "9", "hot": "1111万"},
            {"title": "热门电视剧排行", "rank": "10", "hot": "1000万"}
        ]
        
        news_items = []
        for item in mock_data:
            title = item["title"]
            url = f"https://s.weibo.com/weibo?q={title}"
            
            # 创建唯一ID
            unique_str = f"{self.source_id}:{title}:{url}"
            item_id = self.generate_id(unique_str)
            
            # 创建新闻项
            news_item = self.create_news_item(
                id=item_id,
                title=title,
                url=url,
                content=None,
                summary=None,
                image_url=None,
                published_at=datetime.datetime.now(),
                extra={
                    "rank": item["rank"],
                    "hot": item["hot"],
                    "is_mock": True
                }
            )
            
            news_items.append(news_item)
            
        return news_items
    
    async def parse_response(self, response: Any) -> List[NewsItemModel]:
        """
        解析微博热搜API响应
        """
        try:
            news_items = []
            
            # 如果响应为空或非字典类型，返回空列表
            if not response or not isinstance(response, dict):
                logger.error("Weibo API response is empty or invalid")
                return []
            
            # 从配置中获取数据路径
            data_path = self.config.get("data_path", "data.realtime")
            
            # 解析数据路径
            path_parts = data_path.split(".")
            data = response
            for part in path_parts:
                if isinstance(data, dict) and part in data:
                    data = data[part]
                else:
                    logger.error(f"Data path '{data_path}' not found in response")
                    return []
            
            # 确保数据是列表
            if not isinstance(data, list):
                logger.error(f"Data at path '{data_path}' is not a list")
                return []
            
            # 处理热搜列表
            for index, item in enumerate(data):
                try:
                    # 获取标题
                    title = item.get("word", "")
                    if not title:
                        continue
                    
                    # 获取链接
                    url = item.get("url", "")
                    if not url and title:
                        # 如果没有URL但有标题，构造一个搜索URL
                        url = f"https://s.weibo.com/weibo?q={title}"
                    
                    # 获取热度
                    hot = item.get("num", "")
                    
                    # 获取排名
                    rank = str(index + 1)
                    
                    # 判断是否置顶、新上榜等
                    is_top = item.get("is_top", 0) == 1
                    is_hot = item.get("is_hot", 0) == 1
                    is_new = item.get("is_new", 0) == 1
                    
                    # 创建唯一ID
                    unique_str = f"{self.source_id}:{title}:{url}"
                    item_id = self.generate_id(unique_str)
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        published_at=datetime.datetime.now(),
                        extra={
                            "rank": rank,
                            "hot": hot,
                            "is_top": is_top,
                            "is_new": is_new,
                            "is_hot": is_hot
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing Weibo hot item: {str(e)}")
            
            logger.info(f"Parsed {len(news_items)} items from Weibo hot search API")
            return news_items
        
        except Exception as e:
            logger.error(f"Error parsing Weibo hot search API response: {str(e)}")
            return [] 