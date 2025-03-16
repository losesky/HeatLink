import logging
import re
import json
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.web import WebNewsSource

logger = logging.getLogger(__name__)


class KuaishouHotSearchSource(WebNewsSource):
    """
    快手热搜适配器
    """
    
    def __init__(
        self,
        source_id: str = "kuaishou",
        name: str = "快手热搜",
        url: str = "https://www.kuaishou.com/?isHome=1",
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "video",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
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
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析快手网页响应
        需要从HTML中提取APOLLO_STATE数据
        """
        try:
            news_items = []
            
            # 从HTML中提取APOLLO_STATE数据
            apollo_state_match = re.search(r'window\.__APOLLO_STATE__\s*=\s*(\{.+?\});', response, re.DOTALL)
            if not apollo_state_match:
                logger.error("Failed to extract APOLLO_STATE data from Kuaishou HTML")
                return []
            
            # 解析JSON数据
            apollo_state_json = apollo_state_match.group(1)
            apollo_state = json.loads(apollo_state_json)
            
            # 获取热榜数据ID
            default_client = apollo_state.get("defaultClient", {})
            root_query = default_client.get("ROOT_QUERY", {})
            hot_rank = root_query.get('visionHotRank({"page":"home"})', {})
            hot_rank_id = hot_rank.get("id", "")
            
            if not hot_rank_id:
                logger.error("Failed to find hot rank ID in Kuaishou APOLLO_STATE data")
                return []
            
            # 获取热榜列表数据
            hot_rank_data = default_client.get(hot_rank_id, {})
            items = hot_rank_data.get("items", [])
            
            for item in items:
                try:
                    # 获取热搜项ID
                    item_id = item.get("id", "")
                    if not item_id:
                        continue
                    
                    # 从ID中提取实际的热搜词
                    hot_search_word = item_id.replace("VisionHotRankItem:", "")
                    
                    # 获取具体的热榜项数据
                    hot_item = default_client.get(item_id, {})
                    
                    # 跳过置顶项
                    if hot_item.get("tagType") == "置顶":
                        continue
                    
                    # 获取热搜名称
                    name = hot_item.get("name", "")
                    if not name:
                        continue
                    
                    # 生成唯一ID
                    unique_id = self.generate_id(hot_search_word)
                    
                    # 获取URL
                    url = f"https://www.kuaishou.com/search/video?searchKey={name}"
                    
                    # 获取图标
                    icon_url = hot_item.get("iconUrl", "")
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=unique_id,
                        title=name,
                        url=url,  # 快手的移动版URL与PC版相同
                        content=None,
                        summary=None,
                        image_url=icon_url,
                        published_at=None,
                        extra={"is_top": False, "mobile_url": url, 
                            "source_id": self.source_id,
                            "source_name": self.name,
                            "hot_search_word": hot_search_word
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing Kuaishou hot search item: {str(e)}")
                    continue
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing Kuaishou response: {str(e)}")
            return [] 