import logging
import datetime
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.rest_api import RESTNewsSource

logger = logging.getLogger(__name__)


class LinuxDoNewsSource(RESTNewsSource):
    """
    Linux中国（linux.do）新闻源适配器
    """
    
    def __init__(
        self,
        source_id: str = "linuxdo",
        name: str = "Linux中国",
        api_url: str = "https://linux.do/latest.json?order=created",
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "technology",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None,
        mode: str = "latest"  # 模式：latest 或 hot
    ):
        self.mode = mode
        
        # 根据模式设置API URL
        if mode == "hot":
            api_url = "https://linux.do/top/daily.json"
        
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "application/json"
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
            custom_parser=self.custom_parser
        )
    
    def custom_parser(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """
        自定义解析器，处理Linux中国的JSON数据
        """
        news_items = []
        
        try:
            # 获取主题列表
            topic_list = data.get("topic_list", {})
            topics = topic_list.get("topics", [])
            
            for topic in topics:
                try:
                    # 检查主题是否可见、未归档、未置顶
                    visible = topic.get("visible", False)
                    archived = topic.get("archived", False)
                    pinned = topic.get("pinned", False)
                    
                    if not visible or archived or pinned:
                        continue
                    
                    # 获取主题ID
                    topic_id = topic.get("id")
                    if not topic_id:
                        continue
                    
                    # 获取标题
                    title = topic.get("title")
                    if not title:
                        continue
                    
                    # 生成URL
                    url = f"https://linux.do/t/topic/{topic_id}"
                    
                    # 获取创建时间
                    created_at_str = topic.get("created_at")
                    published_at = None
                    if created_at_str:
                        try:
                            published_at = datetime.datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                        except Exception as e:
                            logger.error(f"Error parsing date {created_at_str}: {str(e)}")
                    
                    # 获取摘要
                    excerpt = topic.get("excerpt")
                    
                    # 获取回复数和点赞数
                    reply_count = topic.get("reply_count", 0)
                    like_count = topic.get("like_count", 0)
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=str(topic_id),
                        title=title,
                        url=url,
                        content=None,
                        summary=excerpt,
                        image_url=None,
                        published_at=published_at,
                        extra={
                            "is_top": False,
                            "mobile_url": url,
                            
                            
                            "like_count": like_count,
                            "comment_count": reply_count,
                            "info": f"👍 {like_count} 💬 {reply_count}"
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing LinuxDo topic: {str(e)}")
                    continue
            
            # 如果是最新模式，按创建时间排序
            if self.mode == "latest":
                news_items.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.now(), reverse=True)
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing LinuxDo response: {str(e)}")
            return []


class LinuxDoLatestNewsSource(LinuxDoNewsSource):
    """
    Linux中国最新主题适配器
    """
    
    def __init__(
        self,
        source_id: str = "linuxdo-latest",
        name: str = "Linux中国最新",
        **kwargs
    ):
        super().__init__(
            source_id=source_id,
            name=name,
            mode="latest",
            **kwargs
        )


class LinuxDoHotNewsSource(LinuxDoNewsSource):
    """
    Linux中国热门主题适配器
    """
    
    def __init__(
        self,
        source_id: str = "linuxdo-hot",
        name: str = "Linux中国热门",
        **kwargs
    ):
        super().__init__(
            source_id=source_id,
            name=name,
            mode="hot",
            **kwargs
        ) 