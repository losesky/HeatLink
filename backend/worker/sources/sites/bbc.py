import logging
import datetime
import re
import hashlib
import os
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
import random
import time
import asyncio
from bs4 import BeautifulSoup

from worker.sources.web import WebNewsSource
from worker.sources.base import NewsItemModel
from worker.utils.http_client import http_client

logger = logging.getLogger(__name__)


class BBCWorldNewsSource(WebNewsSource):
    """
    BBC世界新闻适配器
    通过解析RSS feed获取BBC最新内容
    优先从网络获取，网络请求失败时使用本地模拟文件作为备用
    使用增强的超时和重试机制确保网络请求的可靠性
    """
    
    # 用户代理列表，模拟不同的浏览器
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
    ]
    
    # 备用URL列表，如果主URL无法访问，可以尝试备用URL
    BACKUP_URLS = [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.bbc.co.uk/news/world/rss.xml",
        "https://feeds.bbci.co.uk/news/rss.xml?edition=uk"
    ]
    
    def __init__(
        self,
        source_id: str = "bbc_world",
        name: str = "BBC World News",
        url: str = "https://feeds.bbci.co.uk/news/world/rss.xml",  # RSS feed URL
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "world",
        country: str = "GB",
        language: str = "en",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        
        # 设置模拟文件路径
        mock_file = os.path.join(os.path.dirname(__file__), "bbc_mock.xml")
        logger.info(f"Setting mock file path: {mock_file}")
        
        # 随机选择一个用户代理
        user_agent = random.choice(self.USER_AGENTS)
        
        config.update({
            "headers": {
                "User-Agent": user_agent,
                "Accept": "application/xml,application/rss+xml,text/xml,application/atom+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Cache-Control": "max-age=0",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Pragma": "no-cache",
                "DNT": "1",  # Do Not Track
                "Referer": "https://www.bbc.co.uk/"
            },
            # 增加最大重试次数
            "max_retries": 5,
            # 调整重试延迟（秒）
            "retry_delay": 3,
            # 增加总超时时间（秒）
            "total_timeout": 60,
            # 连接超时（秒）
            "connect_timeout": 20,
            # 读取超时（秒）
            "read_timeout": 40,
            # 默认优先从网络获取，失败时使用模拟文件作为备用
            "use_mock": False,
            "use_mock_as_fallback": True,
            "mock_file": mock_file,
            # 启用缓存以减少重复请求
            "use_cache": True,
            "cache_ttl": 1800,  # 30分钟缓存
            # 启用备用URL
            "use_backup_urls": True,
            "backup_urls": self.BACKUP_URLS,
            # 启用HTTP/2
            "use_http2": True,
            # 启用重定向跟随
            "follow_redirects": True,
            # 启用压缩
            "use_compression": True,
            # 启用随机延迟，避免被识别为爬虫
            "use_random_delay": True,
            "min_delay": 0.5,
            "max_delay": 2.0
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
        
        logger.info(f"Initialized {self.name} adapter with URL: {self.url}")
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析BBC RSS feed
        使用BeautifulSoup解析XML，更好地处理CDATA
        """
        logger.info("Parsing BBC RSS feed")
        
        if not response:
            logger.error("Empty response received")
            return []
        
        try:
            # 检查响应是否包含XML声明
            if not response.strip().startswith('<?xml'):
                # 如果响应是HTML，可能是错误页面
                if '<html' in response.lower():
                    logger.error("Received HTML instead of XML, possibly an error page")
                    # 尝试从HTML中提取错误信息
                    soup = BeautifulSoup(response, 'html.parser')
                    error_title = soup.title.text if soup.title else "Unknown error"
                    logger.error(f"Error page title: {error_title}")
                    return []
            
            # 使用BeautifulSoup解析XML
            soup = BeautifulSoup(response, 'xml')
            logger.debug("Successfully parsed XML using BeautifulSoup")
            
            # 查找所有item元素
            items = soup.find_all('item')
            logger.debug(f"Found {len(items)} items in RSS feed")
            
            # 如果没有找到item元素，尝试其他可能的元素名称
            if not items:
                logger.warning("No 'item' elements found, trying alternative elements...")
                # 尝试查找entry元素（Atom格式）
                items = soup.find_all('entry')
                if items:
                    logger.debug(f"Found {len(items)} 'entry' elements")
            
            news_items = []
            for item in items:
                try:
                    # 提取标题
                    title_elem = item.find('title')
                    if not title_elem or not title_elem.text:
                        logger.debug("No title found in item")
                        continue
                    
                    # 提取标题文本
                    title = title_elem.text.strip()
                    
                    # 提取链接
                    link_elem = item.find('link')
                    url = ""
                    if link_elem:
                        # 处理普通链接元素
                        if link_elem.text:
                            url = link_elem.text.strip()
                        # 处理Atom格式链接（带href属性）
                        elif link_elem.get('href'):
                            url = link_elem['href'].strip()
                    
                    if not url:
                        logger.debug(f"No link found for item: {title}")
                        continue
                    
                    # 提取GUID作为ID
                    guid = None
                    guid_elem = item.find('guid')
                    if guid_elem and guid_elem.text:
                        guid = guid_elem.text.strip()
                        # 如果GUID包含#，取前面部分
                        if '#' in guid:
                            guid = guid.split('#')[0]
                    
                    # 如果没有GUID，从URL生成ID
                    article_id = guid or url
                    # 如果ID是URL，提取最后部分
                    if '/articles/' in article_id:
                        article_id = article_id.split('/articles/')[-1]
                    
                    # 使用哈希生成唯一ID
                    item_id = self.generate_id(article_id)
                    
                    # 提取描述/摘要
                    description = None
                    desc_elem = item.find('description')
                    if desc_elem and desc_elem.text:
                        description = desc_elem.text.strip()
                    
                    # 提取发布日期
                    pub_date = None
                    date_elem = item.find('pubDate')
                    if date_elem and date_elem.text:
                        try:
                            # 解析RSS日期格式
                            pub_date_str = date_elem.text.strip()
                            pub_date = datetime.datetime.strptime(
                                pub_date_str, '%a, %d %b %Y %H:%M:%S %Z'
                            ).replace(tzinfo=datetime.timezone.utc)
                        except Exception as e:
                            logger.debug(f"Error parsing publication date: {str(e)}")
                    
                    # 提取图片URL
                    image_url = None
                    media_thumbnail = item.find('media:thumbnail')
                    if media_thumbnail and media_thumbnail.get('url'):
                        image_url = media_thumbnail['url']
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        content=None,
                        summary=description,
                        image_url=image_url,
                        published_at=pub_date
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing RSS item: {str(e)}")
                    continue
            
            logger.info(f"Parsed {len(news_items)} news items from RSS feed")
            return news_items
            
        except Exception as e:
            logger.error(f"Error parsing RSS feed: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从BBC RSS feed获取最新新闻
        优先从网络获取，网络请求失败时使用本地模拟文件作为备用
        使用增强的超时和重试机制确保网络请求的可靠性
        """
        try:
            logger.info("Fetching BBC world news")
            
            response = None
            
            # 检查是否使用模拟文件
            if self.config.get("use_mock", False):
                mock_file = self.config.get("mock_file")
                logger.info(f"Using mock file: {mock_file}")
                
                if mock_file and os.path.exists(mock_file):
                    logger.info(f"Reading mock file: {mock_file}")
                    try:
                        with open(mock_file, 'r', encoding='utf-8') as f:
                            response = f.read()
                        logger.info(f"Successfully read mock file, content length: {len(response)}")
                    except Exception as e:
                        logger.error(f"Error reading mock file: {str(e)}", exc_info=True)
                        return []
                else:
                    logger.error(f"Mock file not found: {mock_file}")
                    return []
            else:
                # 准备URL列表
                urls_to_try = [self.url]
                if self.config.get("use_backup_urls", True):
                    # 添加备用URL，但确保不重复
                    backup_urls = self.config.get("backup_urls", [])
                    for url in backup_urls:
                        if url != self.url and url not in urls_to_try:
                            urls_to_try.append(url)
                
                # 尝试从网络获取，使用增强的重试机制
                max_retries = self.config.get("max_retries", 5)
                retry_delay = self.config.get("retry_delay", 3)
                
                # 对每个URL进行尝试
                for url_index, current_url in enumerate(urls_to_try):
                    logger.info(f"Trying URL {url_index+1}/{len(urls_to_try)}: {current_url}")
                    
                    # 为每个URL重置重试计数
                    for retry in range(max_retries):
                        try:
                            # 随机延迟，避免被识别为爬虫
                            if self.config.get("use_random_delay", True) and retry > 0:
                                delay = random.uniform(
                                    self.config.get("min_delay", 0.5),
                                    self.config.get("max_delay", 2.0)
                                )
                                logger.debug(f"Random delay before retry: {delay:.2f} seconds")
                                await asyncio.sleep(delay)
                            
                            # 每次请求使用随机的用户代理
                            headers = dict(self.headers)
                            headers["User-Agent"] = random.choice(self.USER_AGENTS)
                            
                            # 添加随机的请求ID，避免缓存问题
                            request_id = f"{int(time.time())}-{random.randint(1000, 9999)}"
                            if "?" in current_url:
                                fetch_url = f"{current_url}&_rid={request_id}"
                            else:
                                fetch_url = f"{current_url}?_rid={request_id}"
                            
                            logger.info(f"Fetching from network (attempt {retry+1}/{max_retries}): {fetch_url}")
                            
                            # 使用HTTP客户端支持的参数
                            response = await http_client.fetch(
                                url=fetch_url,
                                method="GET",
                                headers=headers,
                                response_type="text",
                                timeout=self.config.get("total_timeout", 60),
                                cache=self.config.get("use_cache", True)
                            )
                            
                            # 检查响应是否为空
                            if not response or len(response.strip()) == 0:
                                logger.warning("Received empty response")
                                if retry < max_retries - 1:
                                    continue
                                else:
                                    break
                            
                            logger.info(f"Successfully fetched from network, content length: {len(response)}")
                            break  # 成功获取数据，跳出重试循环
                        except Exception as e:
                            logger.warning(f"Error fetching from network (attempt {retry+1}/{max_retries}): {str(e)}")
                            
                            if retry < max_retries - 1:
                                # 如果还有重试次数，等待一段时间后重试
                                logger.info(f"Retrying in {retry_delay} seconds...")
                                await asyncio.sleep(retry_delay)
                                # 每次重试增加延迟时间，避免频繁请求
                                retry_delay = min(retry_delay * 1.5, 10)
                            else:
                                # 已达到最大重试次数，记录错误
                                logger.error(f"Failed to fetch from URL {current_url} after {max_retries} attempts: {str(e)}", exc_info=True)
                    
                    # 如果成功获取到响应，跳出URL循环
                    if response and len(response.strip()) > 0:
                        logger.info(f"Successfully fetched from URL: {current_url}")
                        break
                
                # 如果所有URL都尝试失败，使用模拟文件作为备用
                if not response or len(response.strip()) == 0:
                    logger.warning("All URLs failed, trying mock file as fallback")
                    if self.config.get("use_mock_as_fallback", True):
                        mock_file = self.config.get("mock_file")
                        if mock_file and os.path.exists(mock_file):
                            logger.info(f"Using mock file as fallback: {mock_file}")
                            with open(mock_file, 'r', encoding='utf-8') as f:
                                response = f.read()
                            logger.info(f"Successfully read mock file as fallback")
                        else:
                            logger.error(f"Mock file not found: {mock_file}")
                            return []
                    else:
                        logger.error("No fallback available, returning empty result")
                        return []
            
            # 解析响应
            news_items = await self.parse_response(response)
            
            return news_items
            
        except Exception as e:
            logger.error(f"Error fetching news: {str(e)}", exc_info=True)
            return [] 