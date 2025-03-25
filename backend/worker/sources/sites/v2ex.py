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


class V2EXHotTopicsSource(WebNewsSource):
    """
    V2EX热门话题适配器
    通过解析RSS feed获取V2EX最新内容
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
        "https://www.v2ex.com/index.xml",
        "https://v2ex.com/index.xml",
        "https://www.v2ex.com/feed/tab/all.xml"
    ]
    
    def __init__(
        self,
        source_id: str = "v2ex",
        name: str = "V2EX热门",
        url: str = "https://www.v2ex.com/index.xml",  # RSS feed URL
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "technology",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        
        # 设置模拟文件路径
        mock_file = os.path.join(os.path.dirname(__file__), "v2ex_mock.xml")
        
        # 随机选择一个用户代理
        user_agent = random.choice(self.USER_AGENTS)
        
        config.update({
            "headers": {
                "User-Agent": user_agent,
                "Accept": "application/xml,application/atom+xml,text/xml,application/rss+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
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
                "Referer": "https://www.v2ex.com/"
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
            # 默认使用模拟文件，因为V2EX可能有反爬虫措施
            "use_mock": False,
            "use_mock_as_fallback": False,
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
        解析RSS feed响应，提取新闻项
        
        Args:
            response: RSS feed响应内容
            
        Returns:
            List[NewsItemModel]: 新闻项列表
        """
        try:
            logger.info("Parsing V2EX RSS feed")
            
            # 检查响应是否为空
            if not response or len(response.strip()) == 0:
                logger.error("Empty response received")
                return []
            
            # 检查响应是否包含XML声明
            if not response.strip().startswith('<?xml'):
                logger.warning("Response does not start with XML declaration, checking content...")
                # 检查是否是HTML响应（可能是错误页面）
                if '<html' in response.lower():
                    logger.error("Received HTML instead of XML, possibly an error page")
                    # 尝试从HTML中提取错误信息
                    soup = BeautifulSoup(response, 'html.parser')
                    error_title = soup.title.text if soup.title else "Unknown error"
                    logger.error(f"Error page title: {error_title}")
                    return []
            
            # 创建命名空间映射
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'dc': 'http://purl.org/dc/elements/1.1/',
                'content': 'http://purl.org/rss/1.0/modules/content/'
            }
            
            # 解析XML
            try:
                root = ET.fromstring(response)
                logger.debug("Successfully parsed XML")
            except ET.ParseError as e:
                logger.error(f"XML parse error: {str(e)}")
                # 尝试修复常见的XML问题
                fixed_response = response
                # 修复未转义的&符号
                fixed_response = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;)', '&amp;', fixed_response)
                # 修复未关闭的标签
                fixed_response = re.sub(r'<([a-zA-Z0-9]+)([^>]*)>([^<]*)', r'<\1\2>\3</\1>', fixed_response)
                
                try:
                    root = ET.fromstring(fixed_response)
                    logger.debug("Successfully parsed XML after fixing issues")
                except ET.ParseError as e2:
                    logger.error(f"Still failed to parse XML after fixes: {str(e2)}")
                    # 最后尝试使用BeautifulSoup解析
                    try:
                        soup = BeautifulSoup(response, 'xml')
                        # 将BeautifulSoup对象转换为字符串，然后再解析为XML
                        root = ET.fromstring(str(soup))
                        logger.debug("Successfully parsed XML using BeautifulSoup")
                    except Exception as e3:
                        logger.error(f"Failed to parse XML with BeautifulSoup: {str(e3)}")
                        return []
            
            # 查找所有entry元素（Atom格式）或item元素（RSS格式）
            entries = root.findall('.//atom:entry', namespaces) or root.findall('.//item')
            
            # 如果没有找到entry或item元素，尝试其他可能的元素名称
            if not entries:
                logger.warning("No 'entry' or 'item' elements found, trying alternative elements...")
                # 尝试查找任何可能包含新闻的元素
                for elem in root.iter():
                    if elem.tag.endswith('item') or elem.tag.endswith('entry'):
                        entries.append(elem)
                logger.debug(f"Found {len(entries)} alternative news elements")
            
            logger.debug(f"Found {len(entries)} entries in RSS feed")
            
            news_items = []
            for entry in entries:
                try:
                    # 提取标题
                    title_elem = entry.find('./atom:title', namespaces) or entry.find('./title')
                    if title_elem is None or not title_elem.text:
                        logger.debug("No title found in entry")
                        continue
                    
                    title = title_elem.text.strip()
                    # 处理CDATA包装
                    if title.startswith('<![CDATA[') and title.endswith(']]>'):
                        title = title[9:-3].strip()
                    
                    # 提取链接
                    link_elem = entry.find('./atom:link[@rel="alternate"]', namespaces) or entry.find('./link')
                    url = ""
                    if link_elem is not None:
                        if link_elem.text:
                            url = link_elem.text.strip()
                        elif link_elem.get('href'):  # Atom格式
                            url = link_elem.get('href').strip()
                    
                    if not url:
                        logger.debug(f"No link found for entry: {title}")
                        continue
                    
                    # 提取ID
                    id_elem = entry.find('./atom:id', namespaces) or entry.find('./guid')
                    topic_id = ""
                    if id_elem is not None and id_elem.text:
                        # 尝试从ID中提取话题ID
                        id_text = id_elem.text.strip()
                        if '/t/' in id_text:
                            topic_id = id_text.split('/t/')[-1].split('#')[0]
                    
                    # 如果无法从ID中提取，则从URL中提取
                    if not topic_id and '/t/' in url:
                        topic_id = url.split('/t/')[-1].split('#')[0]
                    
                    # 如果仍然无法提取，则生成一个基于URL的哈希ID
                    if not topic_id:
                        topic_id = hashlib.md5(url.encode()).hexdigest()
                    
                    # 提取发布时间
                    published_elem = entry.find('./atom:published', namespaces) or entry.find('./pubDate') or entry.find('./dc:date', namespaces)
                    published_at = None
                    if published_elem is not None and published_elem.text:
                        try:
                            date_text = published_elem.text.strip()
                            # 尝试多种日期格式
                            if re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', date_text):  # ISO格式
                                # 处理Z结尾的ISO日期
                                if date_text.endswith('Z'):
                                    date_text = date_text.replace('Z', '+00:00')
                                published_at = datetime.datetime.fromisoformat(date_text)
                            else:  # RFC 822格式
                                from email.utils import parsedate_to_datetime
                                published_at = parsedate_to_datetime(date_text)
                            logger.debug(f"Parsed date: {published_at} from {published_elem.text}")
                        except ValueError as e:
                            logger.debug(f"Invalid published date format: {published_elem.text}, error: {str(e)}")
                            # 如果无法解析日期，使用当前时间
                            published_at = datetime.datetime.now(datetime.timezone.utc)
                    
                    # 提取内容
                    content_elem = entry.find('./atom:content', namespaces) or entry.find('./content:encoded', namespaces) or entry.find('./description')
                    content = ""
                    summary = ""
                    if content_elem is not None and content_elem.text:
                        content = content_elem.text.strip()
                        # 处理CDATA包装
                        if content.startswith('<![CDATA[') and content.endswith(']]>'):
                            content = content[9:-3].strip()
                        # 清理HTML标签
                        soup = BeautifulSoup(content, 'html.parser')
                        clean_content = soup.get_text(separator=' ', strip=True)
                        content = clean_content
                        # 生成摘要
                        summary = content[:200] if len(content) > 200 else content
                    
                    # 提取作者
                    author_elem = entry.find('./atom:author/atom:name', namespaces) or entry.find('./author') or entry.find('./dc:creator', namespaces)
                    author = ""
                    if author_elem is not None:
                        if author_elem.text:
                            author = author_elem.text.strip()
                        elif hasattr(author_elem, 'find') and author_elem.find('./name'):
                            name_elem = author_elem.find('./name')
                            if name_elem is not None and name_elem.text:
                                author = name_elem.text.strip()
                    
                    # 从标题中提取节点信息
                    node = ""
                    node_match = re.match(r'^\[(.*?)\]', title)
                    if node_match:
                        node = node_match.group(1)
                    
                    # 提取图片URL（如果有）
                    image_url = None
                    if content:
                        soup = BeautifulSoup(content, 'html.parser')
                        img_tag = soup.find('img')
                        if img_tag and img_tag.has_attr('src'):
                            image_url = img_tag['src']
                            logger.debug(f"Extracted image from content: {image_url}")
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=topic_id,
                        title=title,
                        url=url,
                        content=content,
                        summary=summary,
                        image_url=image_url,
                        published_at=published_at,
                        extra={
                            "is_top": False, 
                            "mobile_url": url,
                            "node": node,
                            "author": author,
                            "source": "v2ex"
                        }
                    )
                    
                    news_items.append(news_item)
                    logger.debug(f"Added news item: {title}")
                except Exception as e:
                    logger.error(f"Error processing RSS entry: {str(e)}", exc_info=True)
                    continue
            
            logger.info(f"Parsed {len(news_items)} news items from V2EX RSS feed")
            return news_items
            
        except Exception as e:
            logger.error(f"Error parsing V2EX RSS feed: {str(e)}", exc_info=True)
            return []
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从V2EX RSS feed获取最新话题
        优先从网络获取，网络请求失败时使用模拟文件作为备用
        使用增强的超时和重试机制确保网络请求的可靠性
        """
        try:
            logger.info("Fetching V2EX topics")
            
            response = None
            
            # 检查是否使用模拟文件
            if self.config.get("use_mock", False):
                mock_file = self.config.get("mock_file")
                if mock_file and os.path.exists(mock_file):
                    logger.info(f"Using mock file: {mock_file}")
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
            logger.error(f"Error fetching V2EX topics: {str(e)}", exc_info=True)
            return [] 