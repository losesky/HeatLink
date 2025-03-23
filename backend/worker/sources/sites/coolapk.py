import logging
import datetime
import re
import json
import asyncio
import random
from typing import List, Dict, Any, Optional

from bs4 import BeautifulSoup
import aiohttp

from worker.sources.base import NewsItemModel
from worker.sources.web import APINewsSource
from worker.utils.http_client import http_client

logger = logging.getLogger(__name__)


class CoolApkNewsSource(APINewsSource):
    """
    酷安新闻源适配器
    使用网页抓取获取酷安网站内容
    由于API和部分页面不可用，现仅抓取主页和应用页面
    """
    
    # CoolApk web URLs
    MAIN_URL = "https://www.coolapk.com"
    APP_URL = "https://www.coolapk.com/apk"
    
    # Third party source as a last resort
    THIRD_PARTY_URL = "https://api.vvhan.com/api/apptop"
    
    # User agents to rotate
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:94.0) Gecko/20100101 Firefox/94.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/94.0.4606.76 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 11; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.85 Mobile Safari/537.36"
    ]
    
    def __init__(
        self,
        source_id: str = "coolapk",
        name: str = "酷安",
        api_url: str = None,  # Will be set to MAIN_URL by default
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "technology",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        # Use main URL if none provided
        api_url = api_url or self.MAIN_URL
        
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": random.choice(self.USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://www.coolapk.com/"
            },
            "response_type": "text",  # Get raw response as text to parse as HTML
            "max_retries": 3,
            "retry_delay": 2,
            "request_timeout": 15  # 15秒超时
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
            config=config
        )
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从酷安网站抓取内容，包含重试和备用地址
        """
        logger.info(f"Fetching CoolApk data from {self.api_url}")
        
        try:
            # 获取配置参数
            max_retries = self.config.get("max_retries", 3)
            retry_delay = self.config.get("retry_delay", 2)
            timeout = self.config.get("request_timeout", 15)
            
            # 尝试从主要URL抓取数据
            for attempt in range(1, max_retries + 1):
                try:
                    # 更新随机 User-Agent
                    self.headers["User-Agent"] = random.choice(self.USER_AGENTS)
                    
                    logger.info(f"Attempting to fetch from main URL (attempt {attempt}/{max_retries})")
                    items = await self._fetch_from_website(self.api_url, timeout)
                    if items:
                        logger.info(f"Successfully fetched {len(items)} items from main URL")
                        return items
                except Exception as e:
                    error_message = str(e)
                    logger.error(f"Error fetching from main URL (attempt {attempt}/{max_retries}): {error_message}")
                    
                    # 最后一次尝试失败，继续尝试备选URL
                    if attempt >= max_retries:
                        logger.info("All attempts with main URL failed, will try alternative URL")
                        break
                    
                    # 计算重试延迟（使用指数退避策略）
                    current_delay = retry_delay * (1.5 ** (attempt - 1))
                    logger.info(f"Retrying in {current_delay:.2f} seconds...")
                    await asyncio.sleep(current_delay)
            
            # 如果主要URL失败，尝试应用页面
            try:
                # 更新随机 User-Agent
                self.headers["User-Agent"] = random.choice(self.USER_AGENTS)
                
                logger.info(f"Attempting to fetch from app URL: {self.APP_URL}")
                items = await self._fetch_from_website(self.APP_URL, timeout)
                if items:
                    logger.info(f"Successfully fetched {len(items)} items from app URL")
                    return items
            except Exception as e:
                logger.error(f"Error fetching from app URL: {str(e)}")
            
            # 尝试第三方来源
            try:
                # 更新随机 User-Agent
                self.headers["User-Agent"] = random.choice(self.USER_AGENTS)
                
                logger.info(f"Attempting to fetch from third-party URL: {self.THIRD_PARTY_URL}")
                items = await self._fetch_from_third_party(self.THIRD_PARTY_URL, timeout)
                if items:
                    logger.info(f"Successfully fetched {len(items)} items from third-party URL")
                    return items
            except Exception as e:
                logger.error(f"Error fetching from third-party URL: {str(e)}")
            
            # 如果以上方法都失败，抛出异常
            error_msg = "无法获取酷安数据：所有抓取方法均失败"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
            
        except Exception as e:
            logger.error(f"Unexpected error during fetch: {str(e)}", exc_info=True)
            # 不再返回模拟数据，而是重新抛出异常
            raise
    
    async def _fetch_from_website(self, url: str, timeout: int) -> List[NewsItemModel]:
        """
        从网页获取数据并解析
        """
        try:
            # 使用http_client获取数据
            response = await http_client.fetch(
                url=url,
                method="GET",
                headers=self.headers,
                timeout=timeout,
                response_type="text"
            )
            
            if not response:
                logger.error(f"Empty response from {url}")
                return []
            
            # 检查响应是否为JSON错误消息
            if response.startswith('{') and '"code":404' in response:
                logger.error(f"Received 404 JSON response from {url}: {response}")
                return []
            
            # 解析 HTML
            return self._parse_coolapk_html(response, url)
                
        except Exception as e:
            logger.error(f"Error in _fetch_from_website for {url}: {str(e)}")
            raise
    
    async def _fetch_from_third_party(self, url: str, timeout: int) -> List[NewsItemModel]:
        """
        从第三方API获取数据
        """
        try:
            # 使用http_client获取数据
            response = await http_client.fetch(
                url=url,
                method="GET",
                headers=self.headers,
                timeout=timeout,
                response_type="text"
            )
            
            if not response:
                logger.error(f"Empty response from third-party API {url}")
                return []
            
            # 尝试解析JSON
            try:
                data = json.loads(response)
                return self._parse_third_party_json(data)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse third-party API response as JSON: {response[:100]}")
                return []
                
        except Exception as e:
            logger.error(f"Error in _fetch_from_third_party for {url}: {str(e)}")
            raise
    
    def _parse_coolapk_html(self, html: str, source_url: str) -> List[NewsItemModel]:
        """
        解析酷安网站HTML
        """
        try:
            news_items = []
            soup = BeautifulSoup(html, 'html.parser')
            
            # 判断是主页还是应用页
            is_main_page = source_url == self.MAIN_URL or source_url.endswith('/')
            is_app_page = '/apk' in source_url
            
            # 主页解析
            if is_main_page:
                # 查找导航菜单项和可能的内容
                menu_links = soup.select('nav a, .nav a, .navbar a, .menu a, .header a')
                content_blocks = soup.select('.block, .card, .feed, .item, article')
                
                logger.info(f"Found {len(menu_links)} menu links and {len(content_blocks)} content blocks on main page")
                
                # 从导航菜单提取有用的链接
                for idx, link in enumerate(menu_links):
                    if not link.has_attr('href') or not link.get_text(strip=True):
                        continue
                    
                    url = link.get('href')
                    # 处理相对链接
                    if url.startswith('/'):
                        url = f"{self.MAIN_URL}{url}"
                    elif not url.startswith('http'):
                        continue
                    
                    title = link.get_text(strip=True)
                    if not title or len(title) < 2:
                        continue
                    
                    # 生成唯一ID
                    item_id = self.generate_id(f"menu:{url}")
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=f"酷安 - {title}",
                        url=url,
                        content=None,
                        summary=f"酷安网站导航: {title}",
                        image_url=None,
                        published_at=datetime.datetime.now(),
                        extra={
                            "is_top": idx < 5,  # 前几个菜单项标记为置顶
                            "mobile_url": url,
                            "source_from": "main_menu"
                        }
                    )
                    
                    news_items.append(news_item)
                
                # 从内容块中提取信息
                for idx, block in enumerate(content_blocks[:10]):  # 限制数量
                    title_elem = block.select_one('h1, h2, h3, .title, .header')
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    if not title or len(title) < 3:
                        continue
                    
                    # 查找链接
                    link = block.select_one('a')
                    url = None
                    if link and link.has_attr('href'):
                        url = link.get('href')
                        # 处理相对链接
                        if url.startswith('/'):
                            url = f"{self.MAIN_URL}{url}"
                    else:
                        url = f"{self.MAIN_URL}/search?q={title}"
                    
                    # 查找可能的摘要内容
                    summary_elem = block.select_one('p, .description, .summary, .content')
                    summary = None
                    if summary_elem:
                        summary = summary_elem.get_text(strip=True)
                    
                    # 查找可能的图片
                    img = block.select_one('img')
                    image_url = None
                    if img and (img.has_attr('src') or img.has_attr('data-src')):
                        image_url = img.get('src') or img.get('data-src')
                        # 处理相对链接
                        if image_url.startswith('//'):
                            image_url = f"https:{image_url}"
                        elif image_url.startswith('/'):
                            image_url = f"{self.MAIN_URL}{image_url}"
                    
                    # 生成唯一ID
                    item_id = self.generate_id(f"content:{url}")
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        content=None,
                        summary=summary,
                        image_url=image_url,
                        published_at=datetime.datetime.now() - datetime.timedelta(hours=idx),
                        extra={
                            "is_top": False,
                            "mobile_url": url,
                            "source_from": "main_content"
                        }
                    )
                    
                    news_items.append(news_item)
            
            # 应用页解析
            elif is_app_page:
                # 查找应用列表项
                app_items = soup.select('.app-list-item, .app_item, .app, .apk-item')
                
                # 如果找不到特定的应用项，尝试查找通用卡片
                if not app_items:
                    app_items = soup.select('.card, .block, .item')
                
                # 如果仍然找不到，尝试查找包含应用链接的元素
                if not app_items:
                    app_links = soup.select('a[href*="/apk/"]')
                    logger.info(f"Found {len(app_links)} app links on app page")
                    
                    for idx, link in enumerate(app_links[:15]):  # 限制数量
                        url = link.get('href')
                        # 处理相对链接
                        if url.startswith('/'):
                            url = f"{self.MAIN_URL}{url}"
                        
                        title = link.get_text(strip=True)
                        if not title or len(title) < 2:
                            continue
                        
                        # 生成唯一ID
                        item_id = self.generate_id(f"app:{url}")
                        
                        # 创建新闻项
                        news_item = self.create_news_item(
                            id=item_id,
                            title=f"酷安应用 - {title}",
                            url=url,
                            content=None,
                            summary=f"酷安应用: {title}",
                            image_url=None,
                            published_at=datetime.datetime.now() - datetime.timedelta(hours=idx),
                            extra={
                                "is_top": False,
                                "mobile_url": url,
                                "source_from": "app_link"
                            }
                        )
                        
                        news_items.append(news_item)
                else:
                    logger.info(f"Found {len(app_items)} app items on app page")
                    
                    for idx, app in enumerate(app_items[:15]):  # 限制数量
                        # 查找应用标题
                        title_elem = app.select_one('.name, .title, h3, h2')
                        if not title_elem:
                            continue
                        
                        title = title_elem.get_text(strip=True)
                        if not title or len(title) < 2:
                            continue
                        
                        # 查找链接
                        link = app.select_one('a')
                        url = None
                        if link and link.has_attr('href'):
                            url = link.get('href')
                            # 处理相对链接
                            if url.startswith('/'):
                                url = f"{self.MAIN_URL}{url}"
                        else:
                            url = f"{self.APP_URL}?search={title}"
                        
                        # 查找图标
                        icon = app.select_one('img')
                        image_url = None
                        if icon and (icon.has_attr('src') or icon.has_attr('data-src')):
                            image_url = icon.get('src') or icon.get('data-src')
                            # 处理相对链接
                            if image_url.startswith('//'):
                                image_url = f"https:{image_url}"
                            elif image_url.startswith('/'):
                                image_url = f"{self.MAIN_URL}{image_url}"
                        
                        # 查找描述
                        description_elem = app.select_one('.description, .summary, p')
                        description = None
                        if description_elem:
                            description = description_elem.get_text(strip=True)
                        
                        # 生成唯一ID
                        item_id = self.generate_id(f"app:{url}")
                        
                        # 创建新闻项
                        news_item = self.create_news_item(
                            id=item_id,
                            title=f"酷安应用 - {title}",
                            url=url,
                            content=None,
                            summary=description,
                            image_url=image_url,
                            published_at=datetime.datetime.now() - datetime.timedelta(hours=idx),
                            extra={
                                "is_top": False,
                                "mobile_url": url,
                                "source_from": "app_item"
                            }
                        )
                        
                        news_items.append(news_item)
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing HTML from {source_url}: {str(e)}")
            return []
    
    def _parse_third_party_json(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """
        解析第三方API的JSON响应
        """
        try:
            news_items = []
            
            # 检查数据结构
            if not isinstance(data, dict):
                logger.error("Third-party API response is not a dictionary")
                return []
            
            # 检查是否有数据
            items = None
            
            if "data" in data and isinstance(data["data"], list):
                items = data["data"]
            elif "list" in data and isinstance(data["list"], list):
                items = data["list"]
            elif "app" in data and isinstance(data["app"], list):
                items = data["app"]
            elif "result" in data and isinstance(data["result"], list):
                items = data["result"]
            
            if not items:
                logger.error("No items found in third-party API response")
                return []
            
            logger.info(f"Found {len(items)} items in third-party API response")
            
            for idx, item in enumerate(items[:15]):  # 限制数量
                if not isinstance(item, dict):
                    continue
                
                # 提取标题
                title = None
                for key in ["title", "name", "appName", "app_name"]:
                    if key in item and item[key]:
                        title = str(item[key])
                        break
                
                if not title or len(title) < 2:
                    continue
                
                # 提取链接
                url = None
                for key in ["url", "link", "href", "download"]:
                    if key in item and item[key]:
                        url = str(item[key])
                        break
                
                if not url:
                    url = f"{self.APP_URL}?search={title}"
                
                # 提取图片
                image_url = None
                for key in ["icon", "img", "image", "logo", "pic"]:
                    if key in item and item[key]:
                        image_url = str(item[key])
                        break
                
                # 提取描述
                description = None
                for key in ["desc", "description", "summary", "detail"]:
                    if key in item and item[key]:
                        description = str(item[key])
                        break
                
                # 生成唯一ID
                item_id = self.generate_id(f"third_party:{title}")
                
                # 创建新闻项
                news_item = self.create_news_item(
                    id=item_id,
                    title=f"酷安应用 - {title}",
                    url=url,
                    content=None,
                    summary=description,
                    image_url=image_url,
                    published_at=datetime.datetime.now() - datetime.timedelta(hours=idx),
                    extra={
                        "is_top": False,
                        "mobile_url": url,
                        "source_from": "third_party_api"
                    }
                )
                
                news_items.append(news_item)
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing third-party API response: {str(e)}")
            return []
    
    def _create_mock_data(self) -> List[NewsItemModel]:
        """
        创建模拟数据，用于在所有方法都失败时提供兜底方案
        """
        mock_titles = [
            "酷安应用市场上线全新UI设计",
            "安卓13新功能详解：这些变化值得升级",
            "国产手机厂商发布全新旗舰产品",
            "最受欢迎的安卓应用 - 2025年3月榜单",
            "手机拍照技巧：如何拍出专业级照片",
            "科技圈周报：一周热门科技新闻汇总",
            "如何提升手机电池续航能力",
            "安卓系统隐藏功能大揭秘",
            "2025年值得关注的智能手机新品",
            "AI手机助手：让生活更智能"
        ]
        
        mock_items = []
        for i, title in enumerate(mock_titles):
            item_id = self.generate_id(f"mock:{title}")
            published_at = datetime.datetime.now() - datetime.timedelta(hours=i)
            
            mock_item = self.create_news_item(
                id=item_id,
                title=title,
                url="https://www.coolapk.com",
                content=None,
                summary=f"这是关于{title}的模拟摘要内容",
                image_url=None,
                published_at=published_at,
                extra={
                    "is_top": False,
                    "mobile_url": "https://www.coolapk.com",
                    "source_from": "mock_data",
                    "is_mock": True
                }
            )
            
            mock_items.append(mock_item)
        
        logger.info(f"Created {len(mock_items)} mock items as fallback")
        return mock_items
    
    async def parse_response(self, response: Any) -> List[NewsItemModel]:
        """
        解析API响应
        这个方法应该不会被调用，因为我们在fetch方法中直接调用了自定义解析方法
        但我们需要实现它以符合基类要求
        """
        logger.warning("parse_response called directly, this should not happen")
        try:
            if isinstance(response, str):
                if '<html' in response.lower():
                    return self._parse_coolapk_html(response, self.api_url)
                elif response.strip().startswith('{'):
                    try:
                        json_data = json.loads(response)
                        # 检查JSON数据类型并做相应处理
                        if isinstance(json_data, dict):
                            # 尝试提取信息
                            return self._parse_third_party_json(json_data)
                    except json.JSONDecodeError:
                        logger.error("Failed to parse response as JSON")
                        return []
            
            logger.error(f"Unsupported response type: {type(response)}")
            return []
        except Exception as e:
            logger.error(f"Error in parse_response: {str(e)}")
            return []


class CoolApkFeedNewsSource(CoolApkNewsSource):
    """
    酷安动态适配器
    由于feed页面已不可用，重定向到主页
    """
    
    def __init__(
        self,
        source_id: str = "coolapk-feed",
        name: str = "酷安动态",
        api_url: str = None,  # Will fallback to main URL
        **kwargs
    ):
        api_url = self.MAIN_URL  # Always use main URL since feed URL is not available
        super().__init__(
            source_id=source_id,
            name=name,
            api_url=api_url,
            **kwargs
        )


class CoolApkAppNewsSource(CoolApkNewsSource):
    """
    酷安应用适配器
    使用应用页面
    """
    
    def __init__(
        self,
        source_id: str = "coolapk-app",
        name: str = "酷安应用",
        api_url: str = None,  # Will be set to APP_URL
        **kwargs
    ):
        api_url = self.APP_URL  # Always use app URL
        super().__init__(
            source_id=source_id,
            name=name,
            api_url=api_url,
            **kwargs
        ) 