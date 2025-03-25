import logging
import datetime
import re
import hashlib
import os
from typing import List, Dict, Any, Optional
import random
import time
import asyncio
from bs4 import BeautifulSoup
import json

from worker.sources.web import WebNewsSource
from worker.sources.base import NewsItemModel
from worker.utils.http_client import http_client

logger = logging.getLogger(__name__)


class V2EXSeleniumSource(WebNewsSource):
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
            
            # 检查响应类型和内容
            if not response:
                logger.error("Empty response received")
                return []
                
            # 如果响应是字典类型（可能是错误信息）
            if isinstance(response, dict):
                if "error" in response:
                    logger.error(f"Error response received: {response.get('error')}")
                    return []
                else:
                    # 尝试将字典转换为字符串
                    try:
                        response = json.dumps(response)
                        logger.warning("Converted dictionary response to JSON string")
                    except Exception as e:
                        logger.error(f"Failed to convert dictionary response to string: {str(e)}")
                        return []
            
            # 确保响应是字符串类型
            if not isinstance(response, str):
                try:
                    response = str(response)
                    logger.warning(f"Converted non-string response to string type")
                except Exception as e:
                    logger.error(f"Failed to convert response to string: {str(e)}")
                    return []
            
            # 检查响应是否为空
            if len(response.strip()) == 0:
                logger.error("Empty response received after type conversion")
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
                
                # 尝试添加XML声明
                logger.info("Trying to add XML declaration to response")
                response = f'<?xml version="1.0" encoding="UTF-8"?>\n{response}'
            
            # 使用 BeautifulSoup 解析 XML
            try:
                logger.debug("Trying to parse XML with BeautifulSoup")
                soup = BeautifulSoup(response, 'xml')
                
                # 查找所有item元素（RSS格式）
                entries = soup.find_all('item')
                
                # 如果没有找到item元素，尝试atom:entry元素（Atom格式）
                if not entries:
                    entries = soup.find_all('entry')
                
                # 如果还是没有找到，尝试通配符搜索
                if not entries:
                    logger.warning("No 'entry' or 'item' elements found, trying with tag ends-with")
                    entries = []
                    for tag in soup.find_all():
                        if tag.name.endswith('item') or tag.name.endswith('entry'):
                            entries.append(tag)
                
                logger.debug(f"Found {len(entries)} entries in RSS feed")
                
                news_items = []
                for entry in entries:
                    try:
                        # 提取标题
                        title_elem = entry.find('title')
                        if title_elem is None or not title_elem.string:
                            logger.debug("No title found in entry")
                            continue
                        
                        title = title_elem.string.strip()
                        # 处理CDATA包装
                        if title.startswith('<![CDATA[') and title.endswith(']]>'):
                            title = title[9:-3].strip()
                        
                        # 提取链接
                        link = ""
                        link_elem = entry.find('link')
                        if link_elem:
                            # 处理 link 标签的不同形式
                            if link_elem.string:
                                link = link_elem.string.strip()
                            elif link_elem.get('href'):  # Atom格式
                                link = link_elem.get('href').strip()
                            elif link_elem.parent and link_elem.parent.name == 'link':
                                # 可能 link 嵌套在另一个 link 元素内
                                link = link_elem.parent.get('href', '').strip()
                        
                        if not link:
                            logger.debug(f"No link found for entry: {title}")
                            continue
                        
                        # 提取ID
                        id_elem = entry.find('guid') or entry.find('id')
                        topic_id = ""
                        if id_elem and id_elem.string:
                            # 尝试从ID中提取话题ID
                            id_text = id_elem.string.strip()
                            if '/t/' in id_text:
                                topic_id = id_text.split('/t/')[-1].split('#')[0]
                        
                        # 如果无法从ID中提取，则从链接中提取
                        if not topic_id and '/t/' in link:
                            topic_id = link.split('/t/')[-1].split('#')[0]
                        
                        # 如果仍然无法提取，则生成一个基于链接的哈希ID
                        if not topic_id:
                            topic_id = hashlib.md5(link.encode()).hexdigest()
                        
                        # 提取发布时间
                        published_at = None
                        pub_date = entry.find('pubDate') or entry.find('published') or entry.find('date')
                        if pub_date and pub_date.string:
                            try:
                                date_text = pub_date.string.strip()
                                # 尝试多种日期格式
                                if re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', date_text):  # ISO格式
                                    # 处理Z结尾的ISO日期
                                    if date_text.endswith('Z'):
                                        date_text = date_text.replace('Z', '+00:00')
                                    published_at = datetime.datetime.fromisoformat(date_text)
                                else:  # RFC 822格式
                                    from email.utils import parsedate_to_datetime
                                    published_at = parsedate_to_datetime(date_text)
                                logger.debug(f"Parsed date: {published_at} from {date_text}")
                            except ValueError as e:
                                logger.debug(f"Invalid published date format: {date_text}, error: {str(e)}")
                                # 如果无法解析日期，使用当前时间
                                published_at = datetime.datetime.now(datetime.timezone.utc)
                        else:
                            # 若没有日期字段，使用当前时间
                            published_at = datetime.datetime.now(datetime.timezone.utc)
                        
                        # 提取内容
                        content = ""
                        summary = ""
                        content_elem = entry.find('description') or entry.find('content') or entry.find('summary')
                        if content_elem and content_elem.string:
                            content = content_elem.string.strip()
                            # 处理CDATA包装
                            if content.startswith('<![CDATA[') and content.endswith(']]>'):
                                content = content[9:-3].strip()
                            
                            # 检查内容是否像HTML标记，避免BeautifulSoup警告
                            is_likely_html = '<' in content and '>' in content
                            is_likely_filepath = (
                                ('/' in content and '.' in content and len(content.split('/')) > 1) or
                                ('\\' in content and '.' in content and len(content.split('\\')) > 1)
                            )
                            # 过滤路径分隔符的频率过高的情况
                            path_separators_count = content.count('/') + content.count('\\')
                            content_length = len(content)
                            separator_ratio = path_separators_count / content_length if content_length > 0 else 0
                            
                            # 清理HTML标签
                            try:
                                # 只有当内容看起来像HTML或至少不像文件路径时才使用BeautifulSoup解析
                                if is_likely_html and (not is_likely_filepath or separator_ratio < 0.1):
                                    # 使用警告过滤，临时忽略BeautifulSoup的文件路径警告
                                    import warnings
                                    with warnings.catch_warnings():
                                        warnings.filterwarnings("ignore", category=UserWarning, module='bs4')
                                        content_soup = BeautifulSoup(content, 'html.parser')
                                        clean_content = content_soup.get_text(separator=' ', strip=True)
                                        content = clean_content
                                else:
                                    # 如果内容看起来不像HTML，简单地移除所有可能的HTML标签
                                    # 使用简单的正则表达式
                                    clean_content = re.sub(r'<[^>]+>', ' ', content)
                                    clean_content = re.sub(r'\s+', ' ', clean_content).strip()
                                    content = clean_content
                                    logger.debug("Content looks like a file path, using regex to clean HTML tags")
                            except Exception as e:
                                logger.warning(f"Error cleaning HTML content: {str(e)}")
                                # 如果解析失败，尝试用正则表达式移除HTML标签
                                try:
                                    clean_content = re.sub(r'<[^>]+>', ' ', content)
                                    clean_content = re.sub(r'\s+', ' ', clean_content).strip()
                                    content = clean_content
                                except Exception:
                                    # 保留原始内容
                                    pass
                            
                            # 生成摘要
                            summary = content[:200] if len(content) > 200 else content
                        
                        # 提取作者
                        author = ""
                        author_elem = entry.find('author') or entry.find('creator')
                        if author_elem:
                            if author_elem.string:
                                author = author_elem.string.strip()
                            elif author_elem.find('name'):
                                name_elem = author_elem.find('name')
                                if name_elem and name_elem.string:
                                    author = name_elem.string.strip()
                        
                        # 从标题中提取节点信息
                        node = ""
                        node_match = re.match(r'^\[(.*?)\]', title)
                        if node_match:
                            node = node_match.group(1)
                        
                        # 提取图片URL（如果有）
                        image_url = None
                        if content:
                            try:
                                # 检查内容是否像HTML
                                if '<' in content and '>' in content and '<img' in content.lower():
                                    # 使用警告过滤，临时忽略BeautifulSoup的文件路径警告
                                    import warnings
                                    with warnings.catch_warnings():
                                        warnings.filterwarnings("ignore", category=UserWarning, module='bs4')
                                        content_soup = BeautifulSoup(content, 'html.parser')
                                        img_tag = content_soup.find('img')
                                        if img_tag and img_tag.has_attr('src'):
                                            image_url = img_tag['src']
                                            logger.debug(f"Extracted image from content: {image_url}")
                                elif 'src=' in content.lower() and ('jpg' in content.lower() or 'png' in content.lower() or 'gif' in content.lower()):
                                    # 使用正则表达式尝试提取图片URL
                                    img_match = re.search(r'src=[\'"](https?://[^\'"]+?\.(?:jpg|jpeg|png|gif))[\'"]', content, re.IGNORECASE)
                                    if img_match:
                                        image_url = img_match.group(1)
                                        logger.debug(f"Extracted image URL using regex: {image_url}")
                            except Exception as e:
                                logger.warning(f"Error extracting image: {str(e)}")
                        
                        # 创建新闻项
                        news_item = self.create_news_item(
                            id=topic_id,
                            title=title,
                            url=link,
                            content=content,
                            summary=summary,
                            image_url=image_url,
                            published_at=published_at,
                            extra={
                                "is_top": False, 
                                "mobile_url": link,
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
                logger.error(f"Error parsing with BeautifulSoup: {str(e)}", exc_info=True)
                return []
            
        except Exception as e:
            logger.error(f"Error parsing V2EX RSS feed: {str(e)}", exc_info=True)
            return []
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从V2EX RSS feed获取最新话题
        优先从网络获取，使用增强的超时和重试机制确保网络请求的可靠性
        """
        try:
            logger.info("Fetching V2EX topics")
            
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
            response = None
            
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
                            timeout=self.config.get("total_timeout", 60)
                        )
                        
                        # 检查响应是否为空或是否为错误信息
                        if not response:
                            logger.warning("Received empty response")
                            if retry < max_retries - 1:
                                continue
                            else:
                                break
                        
                        # 检查响应是否为字符串，否则可能是包含错误信息的字典
                        if isinstance(response, dict) and "error" in response:
                            error_msg = response.get("error", "Unknown error")
                            logger.warning(f"Received error response: {error_msg}")
                            if retry < max_retries - 1:
                                continue
                            else:
                                break
                        
                        # 确保响应是字符串类型
                        if not isinstance(response, str):
                            response = str(response)
                            
                        # 检查响应内容是否为空
                        if len(response.strip()) == 0:
                            logger.warning("Received empty content")
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
                if response and (isinstance(response, str) and len(response.strip()) > 0 or isinstance(response, dict)):
                    logger.info(f"Successfully fetched from URL: {current_url}")
                    break
            
            # 如果所有URL都尝试失败
            if not response or (isinstance(response, str) and len(response.strip()) == 0):
                logger.error("All URLs failed, returning empty result")
                return []
            
            # 解析响应
            news_items = await self.parse_response(response)
            
            return news_items
            
        except Exception as e:
            logger.error(f"Error fetching V2EX topics: {str(e)}", exc_info=True)
            return [] 