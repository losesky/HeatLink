import logging
import datetime
import re
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.rest_api import RESTNewsSource

logger = logging.getLogger(__name__)


class CoolApkNewsSource(RESTNewsSource):
    """
    酷安新闻源适配器
    """
    
    def __init__(
        self,
        source_id: str = "coolapk",
        name: str = "酷安",
        api_url: str = "https://api.coolapk.com/v6/page/dataList?url=%2Ffeed%2FheadlineV8&title=%E5%A4%B4%E6%9D%A1&page=1",
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
                "User-Agent": "Mozilla/5.0 (Linux; Android 10; Redmi K30 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Mobile Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "X-App-Id": "com.coolapk.market",
                "X-App-Version": "11.0",
                "X-App-Token": self._generate_app_token(),
                "X-Sdk-Int": "29",
                "X-Sdk-Locale": "zh-CN",
                "X-App-Device": "OnePlus7Pro",
                "X-App-Code": "2101202",
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
    
    def _generate_app_token(self) -> str:
        """
        生成酷安API请求所需的token
        注意：这是一个简化版，实际的酷安token生成算法更复杂
        """
        # 简化版token，实际应用中需要实现完整的token生成算法
        return "coolapk_api_token_placeholder"
    
    def custom_parser(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """
        自定义解析器，处理酷安的JSON数据
        """
        news_items = []
        
        try:
            # 获取数据列表
            data_list = data.get("data", [])
            
            for item in data_list:
                try:
                    # 跳过非文章类型
                    entity_type = item.get("entityType")
                    if entity_type != "feed" and entity_type != "article":
                        continue
                    
                    # 获取ID
                    item_id = item.get("id")
                    if not item_id:
                        continue
                    
                    # 获取标题
                    title = item.get("title") or item.get("message")
                    if not title:
                        continue
                    
                    # 清理标题中的HTML标签
                    title = re.sub(r'<[^>]+>', '', title)
                    
                    # 获取URL
                    url = None
                    if entity_type == "feed":
                        url = f"https://www.coolapk.com/feed/{item_id}"
                    elif entity_type == "article":
                        url = f"https://www.coolapk.com/article/{item_id}"
                    
                    if not url:
                        continue
                    
                    # 获取发布时间
                    published_at = None
                    publish_time = item.get("publishDate") or item.get("dateline")
                    if publish_time:
                        try:
                            # 酷安的时间戳是秒级的
                            published_at = datetime.datetime.fromtimestamp(int(publish_time) / 1000)
                        except Exception as e:
                            logger.error(f"Error parsing timestamp {publish_time}: {str(e)}")
                    
                    # 获取摘要
                    summary = item.get("message", "")
                    if summary:
                        # 清理摘要中的HTML标签
                        summary = re.sub(r'<[^>]+>', '', summary)
                        # 限制摘要长度
                        summary = summary[:200] + "..." if len(summary) > 200 else summary
                    
                    # 获取图片
                    image_url = None
                    pic = item.get("pic") or item.get("userAvatar")
                    if pic:
                        image_url = pic
                    
                    # 获取作者
                    author = item.get("username") or item.get("userInfo", {}).get("username")
                    
                    # 获取点赞数
                    like_num = item.get("likenum") or 0
                    
                    # 获取评论数
                    comment_num = item.get("commentnum") or 0
                    
                    # 获取标签
                    tag = item.get("tag")
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=str(item_id),
                        title=title,
                        url=url,
                        mobile_url=url,  # 酷安的移动版URL与PC版相同
                        content=None,
                        summary=summary,
                        image_url=image_url,
                        published_at=published_at,
                        extra={
                            "is_top": False,
                            "mobile_url": url,
                            "source_id": self.source_id,
                            "source_name": self.name,
                            "author": author,
                            "like_num": like_num,
                            "comment_num": comment_num,
                            "tag": tag,
                            "info": tag
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing CoolApk news item: {str(e)}")
                    continue
            
            # 按发布时间排序
            news_items.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.now(), reverse=True)
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing CoolApk response: {str(e)}")
            return []


class CoolApkFeedNewsSource(CoolApkNewsSource):
    """
    酷安动态适配器
    """
    
    def __init__(
        self,
        source_id: str = "coolapk-feed",
        name: str = "酷安动态",
        api_url: str = "https://api.coolapk.com/v6/page/dataList?url=%2Ffeed%2FhomeV8&title=%E5%8A%A8%E6%80%81&page=1",
        **kwargs
    ):
        super().__init__(
            source_id=source_id,
            name=name,
            api_url=api_url,
            **kwargs
        )


class CoolApkAppNewsSource(CoolApkNewsSource):
    """
    酷安应用适配器
    """
    
    def __init__(
        self,
        source_id: str = "coolapk-app",
        name: str = "酷安应用",
        api_url: str = "https://api.coolapk.com/v6/page/dataList?url=%2Fapk%2FhomeV8&title=%E5%BA%94%E7%94%A8&page=1",
        **kwargs
    ):
        super().__init__(
            source_id=source_id,
            name=name,
            api_url=api_url,
            **kwargs
        ) 