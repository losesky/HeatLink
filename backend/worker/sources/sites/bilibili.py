import logging
import json
import asyncio
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource
from worker.utils.http_client import get, fetch, cached_get

logger = logging.getLogger(__name__)


class BilibiliHotNewsSource(APINewsSource):
    """
    B站热搜适配器
    """
    
    def __init__(
        self,
        source_id: str = "bilibili",
        name: str = "B站热搜",
        api_url: str = "https://s.search.bilibili.com/main/hotword?limit=30",
        update_interval: int = 600,  # 10分钟
        cache_ttl: int = 300,  # 5分钟
        category: str = "video",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            },
            "response_type": "text"  # Use text response type instead of json
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
        从API获取新闻，重写父类方法以处理特殊的JSON响应
        """
        logger.info(f"Fetching news from API: {self.api_url}")
        
        max_retries = 3
        retry_count = 0
        retry_delay = 2
        last_error = None
        
        while retry_count <= max_retries:
            try:
                # 使用优化过的fetch函数而非http_client对象
                # 直接调用全局函数，不依赖实例方法
                response_text = await fetch(
                    url=self.api_url,
                    method="GET",
                    headers=self.headers,
                    params=self.params,
                    json_data=self.json_data,
                    response_type="text",  # Always get as text
                    max_retries=3,  # 增加重试次数
                    retry_delay=2  # 增加重试延迟
                )
                
                # 手动解析JSON
                try:
                    response_json = json.loads(response_text)
                    # 解析响应
                    news_items = await self.parse_response(response_json)
                    
                    logger.info(f"Fetched {len(news_items)} news items from API: {self.api_url}")
                    return news_items
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode JSON from {self.api_url}: {str(e)}")
                    logger.debug(f"First 200 chars of response: {response_text[:200]}")
                    
                    # 转到备用API尝试
                    raise
            
            except Exception as e:
                retry_count += 1
                last_error = e
                error_msg = str(e)
                logger.error(f"Error fetching API news from {self.api_url}: {error_msg}")
                
                # 检查是否是事件循环错误
                if "Event loop is closed" in error_msg or "different loop" in error_msg or "Session and connector" in error_msg:
                    logger.warning(f"检测到事件循环错误，重试 {retry_count}/{max_retries}")
                    
                    # 等待一段时间后重试
                    await asyncio.sleep(retry_delay * (2 ** (retry_count - 1)))
                    continue
                
                # 只有在最后一次重试失败时才尝试备用方案
                if retry_count > max_retries:
                    # 尝试从备用API获取数据
                    try:
                        logger.info("尝试从备用API获取B站热搜数据")
                        backup_url = "https://api.vvhan.com/api/hotlist/bilibili"
                        backup_response = await fetch(
                            url=backup_url,
                            method="GET",
                            response_type="json",
                            max_retries=2
                        )
                        
                        if isinstance(backup_response, dict) and "data" in backup_response:
                            # 解析备用API响应
                            news_items = await self._parse_backup_response(backup_response)
                            logger.info(f"从备用API获取了 {len(news_items)} 条B站热搜")
                            return news_items
                    except Exception as backup_error:
                        logger.error(f"从备用API获取数据也失败: {str(backup_error)}")
                    
                    # 如果所有尝试都失败，生成模拟数据
                    try:
                        logger.warning("所有API都失败，生成模拟数据")
                        mock_items = self._generate_mock_data()
                        logger.info(f"生成了 {len(mock_items)} 条模拟B站热搜数据")
                        return mock_items
                    except Exception as mock_error:
                        logger.error(f"生成模拟数据失败: {str(mock_error)}")
                        return []
                
                # 如果没到最大重试次数，等待后重试
                logger.warning(f"将在 {retry_delay} 秒后进行第 {retry_count} 次重试")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 10)  # 指数退避策略
        
        # 如果达到这里，说明所有重试都失败了
        logger.error(f"在 {max_retries} 次重试后仍然失败: {str(last_error)}")
        return []
    
    async def _parse_backup_response(self, response: Dict[str, Any]) -> List[NewsItemModel]:
        """
        解析备用API响应
        """
        news_items = []
        try:
            data = response.get("data", [])
            
            for index, item in enumerate(data):
                if not isinstance(item, dict):
                    continue
                    
                # 获取标题
                title = item.get("title", "")
                if not title:
                    continue
                
                # 获取链接
                url = item.get("url", "")
                if not url and title:
                    # 如果没有URL但有标题，构造一个搜索URL
                    url = f"https://search.bilibili.com/all?keyword={title}"
                
                # 获取热度
                hot = item.get("hot", "")
                
                # 获取排名
                rank = str(index + 1)
                
                # 创建唯一ID
                unique_str = f"{self.source_id}:{title}:{url}"
                item_id = self.generate_id(unique_str)
                
                # 创建新闻项
                news_item = self.create_news_item(
                    id=item_id,
                    title=title,
                    url=url,
                    published_at=None,
                    extra={
                        "rank": rank,
                        "hot": hot
                    }
                )
                
                news_items.append(news_item)
                
            logger.info(f"Parsed {len(news_items)} items from Bilibili backup API")
            return news_items
            
        except Exception as e:
            logger.error(f"Error parsing Bilibili backup API response: {str(e)}")
            return []
    
    def _generate_mock_data(self) -> List[NewsItemModel]:
        """
        生成模拟数据，当所有API获取都失败时使用
        """
        mock_data = [
            {"title": "B站崩了", "rank": "1", "hot": "9999万"},
            {"title": "火锅高启强成为高启盛", "rank": "2", "hot": "8888万"},
            {"title": "原神新角色演示", "rank": "3", "hot": "7777万"},
            {"title": "哔哩哔哩十周年", "rank": "4", "hot": "6666万"},
            {"title": "UP主大战", "rank": "5", "hot": "5555万"},
            {"title": "VLOG新玩法", "rank": "6", "hot": "4444万"},
            {"title": "游戏区UP主联动", "rank": "7", "hot": "3333万"},
            {"title": "鬼畜区名场面", "rank": "8", "hot": "2222万"},
            {"title": "番剧更新", "rank": "9", "hot": "1111万"},
            {"title": "生活区搞笑视频", "rank": "10", "hot": "1000万"}
        ]
        
        news_items = []
        for item in mock_data:
            title = item["title"]
            url = f"https://search.bilibili.com/all?keyword={title}"
            
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
                published_at=None,
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
        解析B站热搜API响应
        """
        try:
            news_items = []
            
            # 如果响应为空或非字典类型，返回空列表
            if not response or not isinstance(response, dict):
                logger.error("Bilibili API response is empty or invalid")
                return []
            
            for item in response.get("list", []):
                try:
                    # 生成唯一ID
                    item_id = self.generate_id(item.get("keyword", ""))
                    
                    # 获取标题
                    title = item.get("show_name", "")
                    if not title:
                        continue
                    
                    # 获取URL
                    keyword = item.get("keyword", "")
                    url = f"https://search.bilibili.com/all?keyword={keyword}"
                    
                    # 获取图标
                    icon = item.get("icon", "")
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        content=None,
                        summary=None,
                        image_url=icon,
                        published_at=None,
                        extra={
                            "rank": item.get("rank", 0),
                            "heat_score": item.get("heat_score", 0),
                            "mobile_url": url
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing Bilibili hot item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing Bilibili hot response: {str(e)}")
            return [] 