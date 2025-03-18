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
import traceback
from urllib.parse import urljoin

try:
    import brotli
    HAS_BROTLI = True
except ImportError:
    HAS_BROTLI = False
    logging.warning("Brotli library not found. Bloomberg adapter may fail to decompress content.")

import aiohttp
from aiohttp.client_exceptions import ClientConnectorError, ClientResponseError, ClientError
from bs4 import BeautifulSoup

from worker.sources.web import WebNewsSource
from worker.sources.base import NewsItemModel
from worker.utils.http_client import http_client

logger = logging.getLogger(__name__)


class BloombergNewsSource(WebNewsSource):
    """
    彭博社新闻适配器
    通过解析RSS feed获取彭博社最新内容
    支持多种分类和区域的新闻
    使用增强的超时和重试机制确保网络请求的可靠性
    """
    
    # 用户代理列表，模拟不同的浏览器
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/96.0.4664.53 Mobile/15E148 Safari/604.1"
    ]
    
    # 不同类型的RSS feed URL，便于扩展
    RSS_FEEDS = {
        "latest": "https://news.google.com/rss/search?q=site:bloomberg.com&hl=en-US&gl=US&ceid=US:en",
        "markets": "https://news.google.com/rss/search?q=site:bloomberg.com+markets&hl=en-US&gl=US&ceid=US:en",
        "business": "https://news.google.com/rss/search?q=site:bloomberg.com+business&hl=en-US&gl=US&ceid=US:en",
        "technology": "https://news.google.com/rss/search?q=site:bloomberg.com+technology&hl=en-US&gl=US&ceid=US:en",
        "politics": "https://news.google.com/rss/search?q=site:bloomberg.com+politics&hl=en-US&gl=US&ceid=US:en",
        "asia": "https://news.google.com/rss/search?q=site:bloomberg.com+asia&hl=en-US&gl=US&ceid=US:en",
        "china": "https://news.google.com/rss/search?q=site:bloomberg.com+china&hl=en-US&gl=US&ceid=US:en"
    }
    
    # 备用URL列表，如果主URL无法访问，可以尝试备用URL
    BACKUP_URLS = [
        "https://news.google.com/rss/search?q=site:bloomberg.com&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=site:bloomberg.com+finance&hl=en-US&gl=US&ceid=US:en"
    ]
    
    # 创建模拟数据时使用的主题
    MOCK_TOPICS = [
        "Global Markets Rally as Central Banks Signal Rate Cuts",
        "Tech Stocks Surge on AI Investment Boom",
        "China's Economy Grows 5% in Q1, Beating Expectations",
        "Federal Reserve Holds Rates Steady, Signals Future Cuts",
        "Oil Prices Rise Amid Middle East Tensions",
        "European Union Unveils New Green Energy Initiative",
        "Bank Profits Exceed Analyst Expectations in Q1 Reports",
        "Cryptocurrency Market Stabilizes After Recent Volatility",
        "Global Supply Chain Issues Continue to Affect Manufacturing",
        "Housing Market Cools as Mortgage Rates Remain Elevated",
        "Automotive Industry Accelerates Electric Vehicle Production",
        "Retail Sales Data Shows Shift in Consumer Spending Patterns",
        "Healthcare Stocks Rally on Breakthrough Drug Approvals",
        "Labor Markets Remain Tight Despite Economic Uncertainty",
        "Japan's Central Bank Adjusts Monetary Policy Stance"
    ]
    
    def __init__(
        self,
        source_id: str = "bloomberg",
        name: str = "彭博社",
        url: str = None,  # 如果为None，将使用RSS_FEEDS["latest"]
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "finance",
        country: str = "US",
        language: str = "en",
        feed_type: str = "latest",  # 使用哪种feed类型
        config: Optional[Dict[str, Any]] = None
    ):
        # 使用指定的feed_type设置URL
        if url is None:
            url = self.RSS_FEEDS.get(feed_type, self.RSS_FEEDS["latest"])
        
        config = config or {}
        
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
                "Referer": "https://www.bloomberg.com/"
            },
            # 增加最大重试次数
            "max_retries": 3,
            # 调整重试延迟（秒）
            "retry_delay": 2,
            # 增加总超时时间（秒）
            "total_timeout": 30,
            # 连接超时（秒）
            "connect_timeout": 10,
            # 读取超时（秒）
            "read_timeout": 20,
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
            "max_delay": 2.0,
            # 新闻正文的CSS选择器
            "content_selector": ".body-content",
            # 保存选定的feed类型
            "feed_type": feed_type
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
        
        logger.info(f"Initialized {self.name} adapter with URL: {self.url} (Feed type: {feed_type})")
    
    async def parse_response(self, content: str, base_url: str = None) -> List[NewsItemModel]:
        """
        解析响应内容，支持多种格式
        @param content: 响应内容文本
        @param base_url: 用于相对链接的基础URL
        @return: 新闻项列表
        """
        if not content:
            logger.warning("Empty response content")
            return []
        
        if base_url is None:
            base_url = self.url
            
        # 检查内容类型
        if '<?xml' in content or '<rss' in content or '<feed' in content:
            # 可能是RSS或Atom格式
            return await self._parse_rss(content)
        elif '<urlset' in content or '<sitemap' in content:
            # 可能是Sitemap格式
            return await self._parse_sitemap(content)
        else:
            # 尝试自动检测格式
            try:
                if '<url>' in content or '<loc>' in content:
                    # 可能是sitemap
                    return await self._parse_sitemap(content)
                elif '<item>' in content or '<entry>' in content:
                    # 可能是RSS或Atom
                    return await self._parse_rss(content)
                else:
                    # 尝试作为XML处理
                    return await self._parse_sitemap(content)
            except Exception as e:
                logger.error(f"Failed to parse response: {e}")
                return []
    
    async def _parse_sitemap(self, xml_content: str) -> List[NewsItemModel]:
        """
        解析Sitemap格式的XML
        """
        try:
            soup = BeautifulSoup(xml_content, 'xml')
            items = []
            
            # 检查是否是Sitemap索引
            sitemapindex = soup.find('sitemapindex')
            if sitemapindex:
                logger.info("Found sitemapindex, processing nested sitemaps")
                sitemaps = sitemapindex.find_all('sitemap')
                for sitemap in sitemaps[:3]:  # 限制只处理前3个子Sitemap，避免请求过多
                    loc = sitemap.find('loc')
                    if loc and loc.text:
                        # 获取并解析子Sitemap
                        try:
                            sitemap_content = await http_client.fetch(
                                url=loc.text,
                                method="GET",
                                headers=self.headers,
                                timeout=15
                            )
                            sitemap_items = await self._parse_sitemap(sitemap_content)
                            items.extend(sitemap_items)
                        except Exception as e:
                            logger.warning(f"Error fetching sub-sitemap {loc.text}: {str(e)}")
                
                return items
            
            # 处理urlset (普通Sitemap)
            urlset = soup.find('urlset')
            if not urlset:
                logger.error("No urlset found in sitemap")
                return []
            
            url_tags = urlset.find_all('url')
            logger.info(f"Found {len(url_tags)} URLs in sitemap")
            
            news_count = 0
            max_items = 50  # 限制只处理最新的50条新闻
            for url_tag in url_tags:
                # 达到最大条目数后停止处理
                if news_count >= max_items:
                    break
                
                loc = url_tag.find('loc')
                if not loc or not loc.text:
                    continue
                
                url = loc.text.strip()
                
                # 过滤掉非文章URL
                if not self._is_article_url(url):
                    continue
                
                # 查找lastmod作为发布时间
                lastmod = url_tag.find('lastmod')
                published_at = None
                if lastmod and lastmod.text:
                    try:
                        published_at = datetime.datetime.fromisoformat(lastmod.text.strip().replace('Z', '+00:00'))
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Error parsing date {lastmod.text}: {str(e)}")
                
                # 查找news:news标签获取更多信息
                news_tag = url_tag.find('news:news')
                title = None
                if news_tag:
                    news_title = news_tag.find('news:title')
                    if news_title:
                        title = news_title.text.strip()
                
                # 如果没有找到标题，使用URL路径的最后一部分
                if not title:
                    title = self._extract_title_from_url(url)
                
                # 使用URL生成唯一ID
                item_id = self.generate_id(url)
                
                # 创建NewsItemModel
                news_item = self.create_news_item(
                    id=item_id,
                    title=title,
                    url=url,
                    content=None,  # 暂不获取详细内容
                    summary=None,  # 暂不获取摘要
                    image_url=None,  # 暂不获取图片
                    published_at=published_at,
                    extra={
                        "mobile_url": url,  # 移动端和PC端URL通常一致
                        "source_from": "bloomberg_sitemap"
                    }
                )
                
                items.append(news_item)
                news_count += 1
            
            return items
            
        except Exception as e:
            logger.error(f"Error parsing sitemap: {str(e)}")
            return []
    
    async def _parse_rss(self, xml_content: str) -> List[NewsItemModel]:
        """
        解析RSS格式的XML
        """
        try:
            soup = BeautifulSoup(xml_content, 'xml')
            items = []
            
            # 查找所有item元素
            item_tags = soup.find_all('item')
            if not item_tags:
                # 尝试查找Atom格式的entry
                item_tags = soup.find_all('entry')
                
            if not item_tags:
                logger.error("No items/entries found in RSS feed")
                return []
                
            logger.info(f"Found {len(item_tags)} items in RSS feed")
            
            for item_tag in item_tags:
                # 提取标题
                title_tag = item_tag.find('title')
                if not title_tag or not title_tag.text:
                    continue
                
                title = self._clean_text(title_tag.text)
                
                # 提取链接
                link_tag = item_tag.find('link')
                url = ""
                if link_tag:
                    # 处理不同的link格式
                    if link_tag.has_attr('href'):
                        url = link_tag['href']
                    elif link_tag.text:
                        url = link_tag.text.strip()
                
                if not url:
                    continue
                
                # 提取发布时间
                published_at = None
                pub_date_tag = item_tag.find('pubDate')
                if not pub_date_tag:
                    pub_date_tag = item_tag.find('published')
                
                if pub_date_tag and pub_date_tag.text:
                    try:
                        # 尝试解析各种格式的日期
                        date_str = pub_date_tag.text.strip()
                        published_at = self._parse_date(date_str)
                    except Exception as e:
                        logger.warning(f"Error parsing date {pub_date_tag.text}: {str(e)}")
                
                # 提取描述/摘要
                summary = None
                description_tag = item_tag.find('description')
                if not description_tag:
                    description_tag = item_tag.find('summary')
                
                if description_tag and description_tag.text:
                    summary = self._clean_text(description_tag.text)
                
                # 提取图片URL
                image_url = None
                media_content = item_tag.find('media:content')
                if media_content and media_content.has_attr('url'):
                    image_url = media_content['url']
                else:
                    # 尝试从enclosure获取
                    enclosure = item_tag.find('enclosure')
                    if enclosure and enclosure.has_attr('url') and enclosure.has_attr('type'):
                        if enclosure['type'].startswith('image/'):
                            image_url = enclosure['url']
                
                # 使用URL生成唯一ID
                item_id = self.generate_id(url)
                
                # 创建NewsItemModel
                news_item = self.create_news_item(
                    id=item_id,
                    title=title,
                    url=url,
                    content=None,  # 暂不获取详细内容
                    summary=summary,
                    image_url=image_url,
                    published_at=published_at,
                    extra={
                        "mobile_url": url,  # 移动端和PC端URL通常一致
                        "source_from": "bloomberg_rss"
                    }
                )
                
                items.append(news_item)
            
            return items
            
        except Exception as e:
            logger.error(f"Error parsing RSS: {str(e)}")
            return []
    
    def _is_article_url(self, url: str) -> bool:
        """
        判断URL是否是文章页面
        """
        # 排除特定页面类型
        excluded_patterns = [
            '/photo/', '/videos/', '/audio/', '/features/', '/games/', '/podcasts/',
            '/authors/', '/topics/', '/tag/', '/category/', '/archive/', '/series/',
            '/about/', '/contact/', '/terms/', '/privacy/', '/sitemap/', '/search/'
        ]
        
        for pattern in excluded_patterns:
            if pattern in url:
                return False
        
        # 常见的彭博社文章URL模式
        article_patterns = [
            r'/news/', r'/articles/', r'/features/', r'/opinion/',
            r'/\d{4}-\d{2}-\d{2}/', r'/\d{4}/\d{2}/\d{2}/'
        ]
        
        for pattern in article_patterns:
            if re.search(pattern, url):
                return True
        
        # Bloomberg文章URL通常包含日期或长数字ID
        if re.search(r'\d{4}-\d{2}-\d{2}', url) or re.search(r'/\d{8,}', url):
            return True
        
        return False
    
    def _extract_title_from_url(self, url: str) -> str:
        """
        从URL中提取标题
        """
        # 尝试提取最后一个路径组件作为标题
        path = url.split('/')[-1]
        
        # 移除.html或其他扩展名
        path = re.sub(r'\.\w+$', '', path)
        
        # 将连字符和下划线替换为空格
        title = re.sub(r'[-_]', ' ', path)
        
        # 将首字母大写
        title = title.title()
        
        return title
    
    def _clean_text(self, text: str) -> str:
        """
        清理文本内容
        """
        if not text:
            return ""
        
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', ' ', text)
        
        # 替换HTML实体
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&apos;', "'")
        text = text.replace('&#39;', "'")
        
        # 移除多余空格
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def _parse_date(self, date_str: str) -> Optional[datetime.datetime]:
        """
        解析各种格式的日期字符串
        """
        if not date_str:
            return None
        
        # 尝试各种日期格式
        date_formats = [
            '%a, %d %b %Y %H:%M:%S %z',  # RFC 822 (常见RSS格式)
            '%a, %d %b %Y %H:%M:%S GMT',
            '%Y-%m-%dT%H:%M:%S%z',  # ISO 8601
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%d %b %Y',
            '%d %B %Y'
        ]
        
        for date_format in date_formats:
            try:
                return datetime.datetime.strptime(date_str, date_format)
            except ValueError:
                continue
        
        # 使用更灵活的解析方法（如果可用）
        try:
            from dateutil import parser
            return parser.parse(date_str)
        except:
            pass
        
        logger.warning(f"Could not parse date: {date_str}")
        return None
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从Bloomberg获取新闻，重写父类方法添加更多错误处理和重试逻辑
        """
        logger.info(f"Fetching news from Bloomberg: {self.url}")
        
        # 创建适当的会话选项，包括Brotli支持（如果可用）
        session_kwargs = {
            "headers": self.headers,
            "timeout": aiohttp.ClientTimeout(
                total=self.config.get("total_timeout", 30),
                connect=self.config.get("connect_timeout", 10),
                sock_read=self.config.get("read_timeout", 20)
            )
        }
        
        if HAS_BROTLI:
            # 如果支持brotli，确保在请求中包含
            session_kwargs["headers"]["Accept-Encoding"] = "gzip, deflate, br"
        
        # 主要URL和备用URL
        urls_to_try = [self.url]
        if self.config.get("use_backup_urls", True) and self.BACKUP_URLS:
            urls_to_try.extend(self.BACKUP_URLS)
        
        try:
            # 创建一个aiohttp会话
            async with aiohttp.ClientSession(**session_kwargs) as session:
                # 尝试所有URL
                for url in urls_to_try:
                    news_items = await self._fetch_from_url(session, url)
                    if news_items:
                        logger.info(f"Successfully fetched {len(news_items)} news items from {url}")
                        return news_items
                
                # 如果所有URL都失败，返回模拟数据
                logger.warning("All URLs failed, returning mock data")
                return self._create_mock_data()
            
        except Exception as e:
            logger.error(f"Unexpected error in fetch: {str(e)}")
            logger.error(traceback.format_exc())
            return self._create_mock_data()
            
    async def _fetch_from_url(self, session: aiohttp.ClientSession, url: str) -> List[NewsItemModel]:
        """从特定URL获取并处理数据，包含重试逻辑"""
        max_retries = self.config.get("max_retries", 3)
        retry_delay = self.config.get("retry_delay", 2)
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Attempt {attempt}/{max_retries} to fetch from {url}")
                
                # 添加随机延迟避免请求过于频繁
                if self.config.get("use_random_delay", True):
                    min_delay = self.config.get("min_delay", 0.5)
                    max_delay = self.config.get("max_delay", 2.0)
                    delay = random.uniform(min_delay, max_delay)
                    await asyncio.sleep(delay)
                
                # 发送请求
                async with session.get(url, ssl=False) as response:
                    if response.status == 200:
                        text = await response.text()
                        news_items = await self.parse_response(text)
                        if news_items:
                            return news_items
                        else:
                            logger.warning(f"No news items found in response from {url}")
                    else:
                        logger.error(f"Error response from {url}: {response.status}")
                
            except (ClientConnectorError, ClientResponseError, ClientError) as e:
                logger.error(f"Error fetching from {url} (attempt {attempt}/{max_retries}): {e}")
            except Exception as e:
                logger.error(f"Unexpected error fetching from {url}: {e}")
                logger.error(traceback.format_exc())
            
            # 如果不是最后一次尝试，则等待后重试
            if attempt < max_retries:
                wait_time = retry_delay * (1.5 ** (attempt - 1))  # 指数退避策略
                logger.info(f"Waiting {wait_time:.2f}s before retry...")
                await asyncio.sleep(wait_time)
        
        # 所有尝试都失败了
        return []
    
    def _create_mock_data(self) -> List[NewsItemModel]:
        """
        创建模拟数据
        当所有API和备用方法都失败时使用
        """
        logger.info("Creating mock Bloomberg news data")
        
        now = datetime.datetime.now(datetime.timezone.utc)
        news_items = []
        
        for i, topic in enumerate(self.MOCK_TOPICS):
            try:
                # 生成唯一ID
                item_id = hashlib.md5(f"mock_bloomberg_{topic}".encode()).hexdigest()
                
                # 计算模拟发布时间（过去24小时内）
                published_at = now - datetime.timedelta(hours=random.randint(1, 24), minutes=random.randint(0, 59))
                
                # 创建模拟URL
                url_title = topic.lower().replace(' ', '-')
                url = f"https://www.bloomberg.com/news/{url_title}-{published_at.strftime('%Y-%m-%d')}"
                
                # 创建模拟摘要
                summary = f"Bloomberg News: {topic}. This is mock data generated when the actual API is unavailable."
                
                news_item = self.create_news_item(
                    id=item_id,
                    title=topic,
                    url=url,
                    content=None,
                    summary=summary,
                    image_url=None,
                    published_at=published_at,
                    extra={
                        "mobile_url": url,
                        "source_from": "mock_data",
                        "is_mock": True,
                        "rank": i + 1
                    }
                )
                
                news_items.append(news_item)
            except Exception as e:
                logger.error(f"Error creating mock item: {str(e)}")
        
        logger.info(f"Created {len(news_items)} mock news items")
        return news_items


class BloombergMarketsNewsSource(BloombergNewsSource):
    """
    彭博社市场新闻适配器
    专注于市场相关新闻
    """
    
    def __init__(
        self,
        source_id: str = "bloomberg-markets",
        name: str = "彭博社市场",
        url: str = None,
        **kwargs
    ):
        # 传递market作为feed_type
        super().__init__(
            source_id=source_id,
            name=name,
            url=url,
            feed_type="markets",
            category="finance",
            **kwargs
        )


class BloombergTechnologyNewsSource(BloombergNewsSource):
    """
    彭博社科技新闻适配器
    专注于科技相关新闻
    """
    
    def __init__(
        self,
        source_id: str = "bloomberg-tech",
        name: str = "彭博社科技",
        url: str = None,
        **kwargs
    ):
        # 传递technology作为feed_type
        super().__init__(
            source_id=source_id,
            name=name,
            url=url,
            feed_type="technology",
            category="technology",
            **kwargs
        )


class BloombergChinaNewsSource(BloombergNewsSource):
    """
    彭博社中国新闻适配器
    专注于中国相关新闻
    """
    
    def __init__(
        self,
        source_id: str = "bloomberg-china",
        name: str = "彭博社中国",
        url: str = None,
        **kwargs
    ):
        # 传递china作为feed_type
        super().__init__(
            source_id=source_id,
            name=name,
            url=url,
            feed_type="china",
            category="finance",
            country="CN",
            **kwargs
        ) 