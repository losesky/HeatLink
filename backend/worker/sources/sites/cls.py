import logging
import datetime
import os
from typing import List, Dict, Any, Optional
import aiohttp
import json
import asyncio

from worker.sources.base import NewsItemModel
from worker.sources.rest_api import RESTNewsSource

logger = logging.getLogger(__name__)


class CLSNewsSource(RESTNewsSource):
    """
    财联社新闻源适配器
    使用免费API获取财经新闻，不需要API密钥
    """
    
    # 免费财经新闻API列表，按优先级排序
    FREE_API_URLS = [
        "https://api.vvhan.com/api/hotlist/zxnew", # 综合新闻，移到最前面尝试
        "https://api.apiopen.top/api/getWangYiNews?page=1&count=30",
        "https://api.oioweb.cn/api/news/financial",
        "https://api.mcloc.cn/finance"
    ]
    
    def __init__(
        self,
        source_id: str = "cls",
        name: str = "财联社",
        api_url: str = None,  # 使用默认的免费API
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
        
        # 使用第一个免费API作为默认API
        if not api_url:
            api_url = self.FREE_API_URLS[0]
        
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
        从免费财经API获取新闻，依次尝试多个API源
        """
        all_items = []
        
        # 尝试所有免费API，直到获取到足够的新闻
        for api_url in self.FREE_API_URLS:
            logger.info(f"Fetching financial news from API: {api_url}")
            
            items = await self._fetch_from_api(api_url)
            
            if items:
                logger.info(f"Successfully fetched {len(items)} items from {api_url}")
                all_items.extend(items)
                
                # 如果已经获取到足够的新闻（至少10条），就停止请求
                if len(all_items) >= 10:
                    break
        
        # 如果仍然没有数据，生成模拟数据（仅开发/测试环境）
        if not all_items:
            logger.warning("All APIs failed, generating mock data")
            all_items = self._create_mock_data()
        
        return all_items
    
    async def _fetch_from_api(self, api_url: str) -> List[NewsItemModel]:
        """从指定API获取财经新闻"""
        try:
            # 创建会话
            async with aiohttp.ClientSession() as session:
                # 发送GET请求，减少超时时间
                async with session.get(api_url, headers=self.headers, timeout=2) as response:
                    if response.status != 200:
                        logger.warning(f"API request failed with status: {response.status}")
                        try:
                            error_text = await response.text()
                            logger.warning(f"Error response text: {error_text[:200]}")
                        except:
                            pass
                        return []
                    
                    # 获取响应文本
                    text = await response.text()
                    data = json.loads(text)
                    
                    # 解析数据
                    if "oioweb" in api_url:
                        return self._parse_oioweb_data(data)
                    elif "apiopen" in api_url:
                        return self._parse_apiopen_data(data)
                    elif "mcloc" in api_url:
                        return self._parse_mcloc_data(data)
                    elif "vvhan" in api_url:
                        return self._parse_vvhan_data(data)
                    else:
                        # 尝试通用解析
                        logger.info(f"Trying generic parser for {api_url}")
                        return self._parse_generic_data(data)
        except aiohttp.ClientConnectorError as e:
            logger.warning(f"连接错误 {api_url}: {str(e)}")
            return []
        except aiohttp.ClientError as e:
            logger.warning(f"客户端错误 {api_url}: {str(e)}")
            return []
        except asyncio.TimeoutError:
            logger.warning(f"请求超时 {api_url}")
            return []
        except json.JSONDecodeError:
            logger.warning(f"JSON解析错误 {api_url}")
            return []
        except Exception as e:
            logger.warning(f"Error fetching from API {api_url}: {str(e)}")
            return []
    
    def _parse_oioweb_data(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """解析OioWeb API的响应数据"""
        news_items = []
        
        try:
            # 检查响应状态
            if data.get("code") != 200 and data.get("code") != 0:
                logger.warning(f"OioWeb API error: {data.get('msg')}")
                return []
            
            # 获取新闻列表
            news_list = data.get("data", [])
            if not news_list:
                logger.warning("No news found in OioWeb API response")
                return []
            
            logger.info(f"Found {len(news_list)} news items from OioWeb API")
            
            # 处理每条新闻
            for i, item in enumerate(news_list):
                try:
                    # 提取必要字段
                    title = item.get("title")
                    if not title:
                        continue
                    
                    # 生成ID
                    item_id = f"oioweb-{hash(title)}"
                    
                    # 获取URL
                    url = item.get("url")
                    if not url:
                        url = f"https://www.cls.cn/telegraph"
                    
                    # 获取发布时间
                    published_at = None
                    pubdate = item.get("time") or item.get("date") or item.get("pubDate")
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
                        image_url=item.get("pic") or item.get("image") or item.get("picUrl"),
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
                    logger.warning(f"Error processing news item: {str(e)}")
            
            return news_items
        except Exception as e:
            logger.warning(f"Error parsing OioWeb data: {str(e)}")
            return []
    
    def _parse_apiopen_data(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """解析APIOpen（网易新闻）API的响应数据"""
        news_items = []
        
        try:
            # 检查响应状态
            if data.get("code") != 200:
                logger.warning(f"APIOpen error: {data.get('message')}")
                return []
            
            # 获取新闻列表
            news_list = data.get("result", {}).get("list", [])
            if not news_list:
                logger.warning("No news found in APIOpen response")
                return []
            
            logger.info(f"Found {len(news_list)} news items from APIOpen API")
            
            # 只保留财经类新闻
            finance_keywords = ["财经", "金融", "股市", "理财", "基金", "债券", "投资", "经济", "财联社", "银行"]
            finance_news = []
            
            for item in news_list:
                title = item.get("title", "")
                category = item.get("category", "")
                
                # 筛选财经新闻
                if category and "财经" in category:
                    finance_news.append(item)
                elif any(keyword in title for keyword in finance_keywords):
                    finance_news.append(item)
            
            # 如果筛选后没有财经新闻，返回一些一般新闻
            if not finance_news and news_list:
                finance_news = news_list[:10]  # 取前10条作为备选
            
            # 处理每条新闻
            for i, item in enumerate(finance_news):
                try:
                    # 提取必要字段
                    title = item.get("title")
                    if not title:
                        continue
                    
                    # 生成ID
                    item_id = f"apiopen-{hash(title)}"
                    
                    # 获取URL
                    url = item.get("path") or item.get("url")
                    if not url:
                        continue
                    
                    # 获取发布时间
                    published_at = None
                    pubdate = item.get("passtime") or item.get("mtime")
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
                        summary=item.get("digest", ""),
                        image_url=item.get("image") or item.get("imgsrc"),
                        published_at=published_at,
                        extra={
                            "source": item.get("source") or "网易财经",
                            "rank": i + 1,
                            "source_id": self.source_id,
                            "mobile_url": url,
                            "category": item.get("category", "财经")
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.warning(f"Error processing news item: {str(e)}")
            
            return news_items
        except Exception as e:
            logger.warning(f"Error parsing APIOpen data: {str(e)}")
            return []
    
    def _parse_mcloc_data(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """解析McLoc API的响应数据"""
        news_items = []
        
        try:
            # McLoc API可能直接返回数组
            news_list = data if isinstance(data, list) else data.get("data", [])
            
            if not news_list:
                logger.warning("No news found in McLoc API response")
                return []
            
            logger.info(f"Found {len(news_list)} news items from McLoc API")
            
            # 处理每条新闻
            for i, item in enumerate(news_list):
                try:
                    # 提取必要字段
                    title = item.get("title")
                    if not title:
                        continue
                    
                    # 生成ID
                    item_id = f"mcloc-{hash(title)}"
                    
                    # 获取URL
                    url = item.get("url") or item.get("link")
                    if not url:
                        continue
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        content=item.get("content", ""),
                        summary=item.get("desc") or item.get("description", ""),
                        image_url=item.get("pic") or item.get("image"),
                        published_at=datetime.datetime.now(),
                        extra={
                            "source": item.get("src") or item.get("source") or "财经新闻",
                            "rank": i + 1,
                            "source_id": self.source_id,
                            "mobile_url": url
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.warning(f"Error processing news item: {str(e)}")
            
            return news_items
        except Exception as e:
            logger.warning(f"Error parsing McLoc data: {str(e)}")
            return []
    
    def _parse_vvhan_data(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """解析VVHan API的响应数据"""
        news_items = []
        
        try:
            # 检查响应状态
            if not data.get("success", False):
                logger.warning("VVHan API returned failure")
                return []
            
            # 获取新闻列表
            news_list = data.get("data", [])
            if not news_list:
                logger.warning("No news found in VVHan API response")
                return []
            
            logger.info(f"Found {len(news_list)} news items from VVHan API")
            
            # 只保留财经类新闻
            finance_keywords = ["财经", "金融", "股市", "理财", "基金", "债券", "投资", "经济", "财联社", "银行"]
            finance_news = []
            
            for item in news_list:
                title = item.get("title", "")
                
                # 筛选财经新闻
                if any(keyword in title for keyword in finance_keywords):
                    finance_news.append(item)
            
            # 如果筛选后没有财经新闻，返回一些一般新闻
            if not finance_news and news_list:
                finance_news = news_list[:10]  # 取前10条作为备选
            
            # 处理每条新闻
            for i, item in enumerate(finance_news):
                try:
                    # 提取必要字段
                    title = item.get("title")
                    if not title:
                        continue
                    
                    # 生成ID
                    item_id = f"vvhan-{hash(title)}"
                    
                    # 获取URL
                    url = item.get("url")
                    if not url:
                        continue
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        content="",
                        summary="",
                        image_url=None,
                        published_at=datetime.datetime.now(),
                        extra={
                            "source": "综合新闻",
                            "rank": i + 1,
                            "source_id": self.source_id,
                            "mobile_url": url
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.warning(f"Error processing news item: {str(e)}")
            
            return news_items
        except Exception as e:
            logger.warning(f"Error parsing VVHan data: {str(e)}")
            return []
    
    def _parse_generic_data(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """尝试通用解析各种API格式"""
        try:
            # 尝试各种常见的数据结构
            news_list = None
            
            if isinstance(data, list):
                news_list = data
            elif "data" in data and isinstance(data["data"], list):
                news_list = data["data"]
            elif "result" in data:
                if isinstance(data["result"], list):
                    news_list = data["result"]
                elif isinstance(data["result"], dict) and "list" in data["result"]:
                    news_list = data["result"]["list"]
            elif "list" in data:
                news_list = data["list"]
            elif "newslist" in data:
                news_list = data["newslist"]
            
            if not news_list:
                logger.warning("Could not find news list in generic data structure")
                return []
            
            logger.info(f"Found {len(news_list)} items using generic parser")
            
            # 处理新闻
            news_items = []
            for i, item in enumerate(news_list):
                try:
                    # 尝试找到标题 (常见的字段名)
                    title = None
                    for key in ['title', 'name', 'headline', 'subject', 'text']:
                        if key in item and item[key]:
                            title = item[key]
                            break
                    
                    if not title:
                        continue
                    
                    # 尝试找到URL (常见的字段名)
                    url = None
                    for key in ['url', 'link', 'href', 'web_url', 'source_url']:
                        if key in item and item[key]:
                            url = item[key]
                            break
                    
                    if not url:
                        continue
                    
                    # 生成ID
                    item_id = f"generic-{hash(title)}"
                    
                    # 尝试找到内容和摘要
                    content = None
                    for key in ['content', 'body', 'text', 'article', 'description']:
                        if key in item and item[key]:
                            content = item[key]
                            break
                    
                    summary = None
                    for key in ['summary', 'desc', 'description', 'abstract', 'digest']:
                        if key in item and item[key]:
                            summary = item[key]
                            break
                    
                    # 尝试找到图片URL
                    image_url = None
                    for key in ['image', 'image_url', 'img', 'thumbnail', 'pic', 'picUrl']:
                        if key in item and item[key]:
                            image_url = item[key]
                            break
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        content=content or "",
                        summary=summary or "",
                        image_url=image_url,
                        published_at=datetime.datetime.now(),
                        extra={
                            "source": item.get("source") or "新闻源",
                            "rank": i + 1,
                            "source_id": self.source_id,
                            "mobile_url": url
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.warning(f"Error in generic parsing for item {i}: {str(e)}")
            
            return news_items
        except Exception as e:
            logger.warning(f"Error in generic data parsing: {str(e)}")
            return []
    
    def custom_parser(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """
        通用解析器，尝试根据数据结构智能选择合适的解析方法
        """
        return self._parse_generic_data(data)
    
    def _create_mock_data(self) -> List[NewsItemModel]:
        """
        生成模拟财经新闻数据，用于API失效时
        """
        news_items = []
        current_time = datetime.datetime.now()
        
        # 生成模拟新闻
        mock_news = [
            {
                "title": "央行发布货币政策执行报告",
                "summary": "报告指出，将继续实施稳健的货币政策，保持流动性合理充裕，促进经济高质量发展",
                "url": "https://www.example.com/finance/1",
                "published_at": current_time - datetime.timedelta(minutes=30)
            },
            {
                "title": "IMF上调中国经济增长预期",
                "summary": "国际货币基金组织上调对中国经济增长的预期，认为中国经济正展现强劲复苏势头",
                "url": "https://www.example.com/finance/2",
                "published_at": current_time - datetime.timedelta(hours=1)
            },
            {
                "title": "A股三大指数全线上涨",
                "summary": "今日A股市场表现强劲，三大指数全线上涨，科技股表现尤为亮眼，带动大盘走高",
                "url": "https://www.example.com/finance/3",
                "published_at": current_time - datetime.timedelta(hours=2)
            },
            {
                "title": "美联储暗示可能降息",
                "summary": "美联储主席暗示今年可能开始降息，美股市场迅速做出反应，三大指数集体上涨",
                "url": "https://www.example.com/finance/4",
                "published_at": current_time - datetime.timedelta(hours=3)
            },
            {
                "title": "CPI同比上涨2.1%",
                "summary": "最新数据显示，全国居民消费价格指数(CPI)同比上涨2.1%，工业生产者出厂价格指数(PPI)同比下降1.2%",
                "url": "https://www.example.com/finance/5",
                "published_at": current_time - datetime.timedelta(hours=4)
            },
            {
                "title": "央企年报营收利润双增长",
                "summary": "多家央企发布年报，大部分企业营收和净利润实现双增长，显示出较强的发展韧性",
                "url": "https://www.example.com/finance/6",
                "published_at": current_time - datetime.timedelta(hours=5)
            }
        ]
        
        # 创建新闻项
        for i, news in enumerate(mock_news):
            mock_id = f"mock_finance_{i+1}"
            
            item = self.create_news_item(
                id=mock_id,
                title=news["title"],
                url=news["url"],
                summary=news["summary"],
                content=news["summary"],
                published_at=news["published_at"],
                extra={
                    "is_mock": True,
                    "source": "财联社(模拟数据)",
                    "type": "财经新闻"
                }
            )
            
            news_items.append(item)
        
        logger.info(f"Created {len(news_items)} mock financial news items")
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