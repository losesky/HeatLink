import json
import logging
import datetime
from typing import List, Dict, Any

from worker.sources.base import NewsSource, NewsItemModel

logger = logging.getLogger(__name__)


class ZhihuHotNewsSource(NewsSource):
    """
    知乎热榜适配器
    """
    def __init__(self, **kwargs):
        super().__init__(
            source_id="zhihu",
            name="知乎热榜",
            category="social",
            country="CN",
            language="zh-CN",
            update_interval=600,  # 10分钟更新一次
            config=kwargs
        )
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        抓取知乎热榜
        """
        logger.info("Fetching Zhihu hot topics")
        
        url = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=50&desktop=true"
        
        try:
            # 获取 HTTP 客户端
            client = await self.http_client
            
            async with client.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch Zhihu hot topics: {response.status}")
                    return []
                
                data = await response.json()
                
                if not data or "data" not in data:
                    logger.error("Invalid response from Zhihu API")
                    return []
                
                items = []
                for item_data in data["data"]:
                    try:
                        target = item_data.get("target", {})
                        
                        # 获取标题
                        title = target.get("title", "")
                        if not title and "question" in target:
                            title = target.get("question", {}).get("title", "")
                        
                        # 获取URL - 修复URL构建逻辑
                        url = ""
                        if "url" in target:
                            # API返回的URL通常是API格式，需要转换为网页可访问格式
                            api_url = target.get("url", "")
                            # 检查是否是API URL格式
                            if "api.zhihu.com/questions/" in api_url:
                                # 从API URL中提取问题ID
                                question_id = api_url.split("questions/")[-1].split("?")[0].split("/")[0]
                                url = f"https://www.zhihu.com/question/{question_id}"
                            else:
                                # 其他类型的URL，可能需要进一步处理
                                url = api_url.replace("api.zhihu.com", "www.zhihu.com")
                                url = url.replace("questions/", "question/")
                        elif "question" in target and target.get("question", {}).get("id"):
                            # 针对问题类型的内容
                            question_id = target.get("question", {}).get("id")
                            url = f"https://www.zhihu.com/question/{question_id}"
                        elif "id" in target and target.get("type") == "answer":
                            # 针对回答类型的内容
                            answer_id = target.get("id")
                            question_id = target.get("question", {}).get("id", "")
                            url = f"https://www.zhihu.com/question/{question_id}/answer/{answer_id}"
                        elif "id" in target and target.get("type") in ["article", "zvideo"]:
                            # 针对文章或视频
                            content_id = target.get("id")
                            content_type = target.get("type")
                            url = f"https://www.zhihu.com/{content_type}/{content_id}"
                        else:
                            # 如果都无法匹配，构建一个基本URL
                            url = "https://www.zhihu.com"
                        
                        # 获取摘要
                        excerpt = target.get("excerpt", "")
                        
                        # 获取热度
                        metrics = item_data.get("detail_text", "")
                        
                        # 创建新闻项
                        news_item = self.create_news_item(
                            id=self.generate_id(url, title),
                            title=title,
                            url=url,
                            summary=excerpt,
                            published_at=datetime.datetime.now(),
                            extra={
                                "metrics": metrics
                            }
                        )
                        
                        items.append(news_item)
                    except Exception as e:
                        logger.error(f"Error processing Zhihu item: {str(e)}")
                
                logger.info(f"Fetched {len(items)} items from Zhihu hot topics")
                return items
        
        except Exception as e:
            logger.error(f"Error fetching Zhihu hot topics: {str(e)}")
            return [] 