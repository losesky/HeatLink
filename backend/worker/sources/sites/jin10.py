import logging
import re
import json
import datetime
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.web import WebNewsSource
from worker.utils.http_client import http_client

logger = logging.getLogger(__name__)


class Jin10NewsSource(WebNewsSource):
    """
    金十数据快讯适配器
    """
    
    def __init__(
        self,
        source_id: str = "jin10",
        name: str = "金十数据快讯",
        url: str = "https://www.jin10.com/flash_newest.js",
        update_interval: int = 600,  # 10分钟
        cache_ttl: int = 300,  # 5分钟
        category: str = "finance",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://www.jin10.com/"
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
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从金十数据获取快讯
        需要添加时间戳参数
        """
        try:
            # 添加时间戳参数
            timestamp = int(datetime.datetime.now().timestamp() * 1000)
            url = f"{self.url}?t={timestamp}"
            
            # 获取快讯数据
            client = await self.http_client
            async with client.get(
                url=url,
                headers=self.headers
            ) as response:
                response_text = await response.text()
                # 解析响应
                return await self.parse_response(response_text)
            
        except Exception as e:
            logger.error(f"Error fetching Jin10 news: {str(e)}")
            raise
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析金十数据快讯响应
        需要从JS变量中提取JSON数据
        """
        try:
            news_items = []
            
            # 从JS变量中提取JSON数据
            json_str = response.replace("var newest = ", "").replace(";", "").strip()
            data = json.loads(json_str)
            
            # 过滤数据
            filtered_data = [item for item in data if (item.get("data", {}).get("title") or item.get("data", {}).get("content")) and not item.get("channel", []) or 5 not in item.get("channel", [])]
            
            for item in filtered_data:
                try:
                    # 获取ID
                    item_id = item.get("id", "")
                    if not item_id:
                        continue
                    
                    # 获取内容
                    data_obj = item.get("data", {})
                    text = data_obj.get("title") or data_obj.get("content", "")
                    if not text:
                        continue
                    
                    # 清理文本
                    text = re.sub(r'</?b>', '', text)
                    
                    # 提取标题和描述
                    title_match = re.match(r'^【([^】]*)】(.*)$', text)
                    if title_match:
                        title = title_match.group(1)
                        description = title_match.group(2)
                    else:
                        title = text
                        description = None
                    
                    # 获取URL
                    url = f"https://flash.jin10.com/detail/{item_id}"
                    
                    # 获取发布时间
                    time_str = item.get("time", "")
                    published_at = None
                    if time_str:
                        try:
                            # 尝试解析相对日期
                            now = datetime.datetime.now()
                            if "分钟前" in time_str:
                                minutes = int(time_str.replace("分钟前", ""))
                                published_at = now - datetime.timedelta(minutes=minutes)
                            elif "小时前" in time_str:
                                hours = int(time_str.replace("小时前", ""))
                                published_at = now - datetime.timedelta(hours=hours)
                            elif ":" in time_str:  # 今天的时间或完整日期时间
                                if "-" in time_str:  # 完整日期时间格式 (2025-03-15 22:38:21)
                                    try:
                                        published_at = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                                    except ValueError:
                                        # 尝试没有秒的格式 (2025-03-15 22:38)
                                        published_at = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                                else:  # 只有时间 (22:38)
                                    hour, minute = map(int, time_str.split(':'))
                                    published_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                            else:
                                # 尝试解析完整日期时间
                                try:
                                    published_at = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                                except ValueError:
                                    pass
                        except Exception as e:
                            logger.error(f"Error parsing date {time_str}: {str(e)}")
                    
                    # 获取重要性
                    is_important = bool(item.get("important", 0))
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=item_id,
                        title=title,
                        url=url,  # 金十数据的移动版URL与PC版相同
                        content=description,
                        summary=description,
                        image_url=None,
                        published_at=published_at,
                        extra={"is_top": is_important, "mobile_url": url, 
                            "source_id": self.source_id,
                            "source_name": self.name,
                            "is_important": is_important,
                            "tags": item.get("tags", [])
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing Jin10 news item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing Jin10 response: {str(e)}")
            return [] 