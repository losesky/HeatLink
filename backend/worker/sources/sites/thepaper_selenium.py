import sys; sys.path.append('/home/losesky/HeatLink/backend')

import logging
import datetime
import re
import hashlib
import os
import time
import random
import asyncio
import platform
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

# Selenium相关导入
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

from worker.sources.web import WebNewsSource
from worker.sources.base import NewsItemModel
from worker.utils.http_client import http_client

logger = logging.getLogger(__name__)


class ThePaperSeleniumSource(WebNewsSource):
    """
    澎湃新闻热榜适配器 - Selenium版本
    !!!优先使用第三方API获取数据，遇到问题再尝试使用Selenium!!!
    """
    
    # 用户代理列表，模拟不同的浏览器
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
    ]
    
    # 第三方API URL
    THIRD_PARTY_API_URL = "https://api.vvhan.com/api/hotlist/pengPai"
    
    def __init__(
        self,
        source_id: str = "thepaper_selenium",
        name: str = "澎湃新闻热榜",
        url: str = "https://www.thepaper.cn/",
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "news",
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
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
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
            },
            # API配置
            "use_api": True,  # 默认使用API
            "api_url": self.THIRD_PARTY_API_URL,
            "api_timeout": 10,  # API请求超时时间（秒）
            # Selenium配置
            "use_selenium": True,
            "selenium_timeout": 30,  # 页面加载超时时间（秒）
            "selenium_wait_time": 5,  # 等待元素出现的时间（秒）
            "headless": True,  # 无头模式（不显示浏览器窗口）
            # 重试配置
            "max_retries": 3,
            "retry_delay": 5,
            # 启用缓存以减少重复请求
            "use_cache": True,
            "cache_ttl": 1800,  # 30分钟缓存
            # 启用随机延迟，避免被识别为爬虫
            "use_random_delay": True,
            "min_delay": 1.0,
            "max_delay": 3.0,
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
        
        self._driver = None
        logger.info(f"Initialized {self.name} adapter with URL: {self.url}")
        
        # 设置API URL
        self.api_url = config.get("api_url", self.THIRD_PARTY_API_URL)
        logger.info(f"Using API URL: {self.api_url}")
    
    def _create_driver(self):
        """
        创建并配置Selenium WebDriver
        """
        try:
            chrome_options = Options()
            
            # 设置无头模式（不显示浏览器窗口）
            if self.config.get("headless", False):
                chrome_options.add_argument("--headless")
            
            # 设置用户代理
            chrome_options.add_argument(f"--user-agent={random.choice(self.USER_AGENTS)}")
            
            # 禁用GPU加速（在无头模式下可能导致问题）
            chrome_options.add_argument("--disable-gpu")
            
            # 禁用扩展
            chrome_options.add_argument("--disable-extensions")
            
            # 禁用沙盒（在Docker容器中可能需要）
            chrome_options.add_argument("--no-sandbox")
            
            # 禁用开发者工具
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            # 禁用自动化控制提示
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            
            # 设置窗口大小
            chrome_options.add_argument("--window-size=1920,1080")
            
            # 启用JavaScript
            chrome_options.add_argument("--enable-javascript")
            
            # 设置语言
            chrome_options.add_argument("--lang=zh-CN")
            
            # 设置接受Cookie
            chrome_options.add_argument("--enable-cookies")
            
            # 使用webdriver-manager自动下载匹配的ChromeDriver
            try:
                # 尝试使用webdriver-manager自动下载匹配的ChromeDriver
                logger.info("Using webdriver-manager to download matching ChromeDriver")
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e:
                logger.warning(f"Failed to use webdriver-manager: {str(e)}")
                # 尝试使用系统路径
                logger.info("Trying system ChromeDriver paths")
                system = platform.system()
                if system == "Windows":
                    executable_path = './resource/chromedriver.exe'
                elif system == "Linux":
                    # 尝试多个可能的路径
                    possible_paths = [
                        '/usr/bin/chromedriver',
                        '/usr/local/bin/chromedriver',
                        '/snap/bin/chromedriver'
                    ]
                    executable_path = None
                    for path in possible_paths:
                        if os.path.exists(path):
                            executable_path = path
                            break
                    if not executable_path:
                        raise Exception("ChromeDriver not found in common Linux paths")
                else:
                    raise Exception("Unsupported system detected")
                
                logger.info(f"Using ChromeDriver at: {executable_path}")
                service = Service(executable_path=executable_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # 设置页面加载超时
            driver.set_page_load_timeout(self.config.get("selenium_timeout", 30))
            
            # 设置脚本执行超时
            driver.set_script_timeout(self.config.get("selenium_timeout", 30))
            
            logger.info("Successfully created Chrome WebDriver")
            return driver
            
        except Exception as e:
            logger.error(f"Error creating Chrome WebDriver: {str(e)}", exc_info=True)
            return None
    
    async def _get_driver(self):
        """
        获取WebDriver实例，如果不存在则创建
        """
        if self._driver is None:
            # 在事件循环中运行阻塞的WebDriver创建
            loop = asyncio.get_event_loop()
            self._driver = await loop.run_in_executor(None, self._create_driver)
        return self._driver
    
    async def _close_driver(self):
        """
        关闭WebDriver
        """
        if self._driver is not None:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._driver.quit)
                logger.info("Successfully closed Chrome WebDriver")
            except Exception as e:
                logger.error(f"Error closing Chrome WebDriver: {str(e)}", exc_info=True)
            finally:
                self._driver = None
    
    async def close(self):
        """
        关闭资源
        """
        await self._close_driver()
        await super().close()
    
    async def _fetch_with_selenium(self) -> str:
        """
        使用Selenium从澎湃新闻获取页面内容
        """
        driver = await self._get_driver()
        if driver is None:
            logger.error("Failed to create WebDriver")
            return ""
        
        html_content = ""
        try:
            # 随机延迟，模拟人类行为
            if self.config.get("use_random_delay", True):
                delay = random.uniform(
                    self.config.get("min_delay", 1.0),
                    self.config.get("max_delay", 3.0)
                )
                logger.debug(f"Random delay before request: {delay:.2f} seconds")
                await asyncio.sleep(delay)
            
            # 访问页面
            logger.info(f"Opening URL: {self.url}")
            loop = asyncio.get_event_loop()
            
            # 使用超时控制
            try:
                page_load_timeout = self.config.get("selenium_timeout", 30)
                logger.info(f"Setting page load timeout to {page_load_timeout} seconds")
                
                # 设置超时
                await loop.run_in_executor(
                    None, 
                    lambda: driver.set_page_load_timeout(page_load_timeout)
                )
                
                # 访问URL
                await loop.run_in_executor(None, lambda: driver.get(self.url))
                logger.info("Successfully navigated to the URL")
            except Exception as e:
                logger.error(f"Error loading page: {str(e)}")
                
                # 尝试使用JavaScript导航（可能绕过某些超时问题）
                try:
                    logger.info("Attempting to navigate using JavaScript")
                    await loop.run_in_executor(
                        None,
                        lambda: driver.execute_script(f"window.location.href = '{self.url}';")
                    )
                    
                    # 等待页面加载
                    await asyncio.sleep(10)
                    logger.info("Successfully navigated using JavaScript")
                except Exception as js_e:
                    logger.error(f"Error navigating using JavaScript: {str(js_e)}")
                    return ""
            
            # 等待页面加载完成
            wait_time = self.config.get("selenium_wait_time", 5)
            logger.info(f"Waiting for page elements with timeout {wait_time} seconds")
            
            # 添加多个尝试查找热榜容器的选择器
            selectors_found = False
            
            try:
                # 等待热榜容器元素加载完成
                # 使用可能的几种选择器尝试查找热榜容器
                selectors = [
                    'div.index_ppreport__slNZB',  # 主要选择器
                    'div.index_content___Uhtm',   # 内容区域选择器
                    'div.mdCard',                 # 卡片选择器
                    'ul li a.index_inherit__A1ImK', # 链接选择器
                    'div.history_list__P7pVQ',    # 历史列表
                    'div.home_wrapper__H8fk4',    # 首页包装
                    'div.card_wrapper__jgiJB',    # 卡片包装
                    'div[class*="report"]',       # 含report的div
                    'div[class*="content"]',      # 含content的div
                    'ul li',                      # 列表项
                    'div.content',                # 内容区域
                    'div.mdCardBox',              # 卡片盒子
                ]
                
                for selector in selectors:
                    try:
                        logger.debug(f"Trying to find element with selector: {selector}")
                        element = await loop.run_in_executor(
                            None,
                            lambda: WebDriverWait(driver, wait_time).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                            )
                        )
                        logger.info(f"Found element with selector: {selector}")
                        selectors_found = True
                        break
                    except TimeoutException:
                        logger.warning(f"Timeout waiting for element with selector: {selector}")
                        continue
                    except Exception as sel_e:
                        logger.warning(f"Error finding element with selector {selector}: {str(sel_e)}")
                        continue
                
                # 如果找不到任何选择器，尝试等待页面完全加载
                if not selectors_found:
                    logger.warning("No selectors found, waiting for page to load completely")
                    await asyncio.sleep(15)  # 等待更长时间让页面完成渲染
                
                # 等待一些额外时间让JavaScript完成渲染
                logger.info("Waiting additional time for JavaScript rendering")
                await asyncio.sleep(3)
                
            except TimeoutException:
                logger.warning(f"Timeout waiting for hot news container after {wait_time} seconds")
                # 即使超时，我们仍然可以尝试获取页面源码
            except Exception as e:
                logger.error(f"Unexpected error while waiting for elements: {str(e)}")
            
            # 获取页面源代码
            logger.info("Getting page source")
            try:
                html_content = await loop.run_in_executor(None, lambda: driver.page_source)
                content_length = len(html_content or "")
                logger.info(f"Successfully fetched page content with Selenium, content length: {content_length}")
                
                # 保存调试信息
                if content_length > 0:
                    debug_file = self.config.get("debug_file", "")
                    if debug_file:
                        try:
                            with open(debug_file, 'w', encoding='utf-8') as f:
                                f.write(html_content)
                            logger.info(f"Saved content to debug file: {debug_file}")
                        except Exception as e:
                            logger.error(f"Error saving debug file: {str(e)}")
                
                # 随机滚动页面，模拟人类行为
                try:
                    logger.debug("Performing random scroll actions")
                    await loop.run_in_executor(
                        None,
                        lambda: driver.execute_script(
                            "window.scrollTo(0, Math.floor(Math.random() * document.body.scrollHeight / 2));"
                        )
                    )
                    await asyncio.sleep(1)
                    await loop.run_in_executor(
                        None,
                        lambda: driver.execute_script(
                            "window.scrollTo(0, Math.floor(Math.random() * document.body.scrollHeight));"
                        )
                    )
                except Exception as scroll_e:
                    logger.warning(f"Error during scrolling: {str(scroll_e)}")
                
                return html_content
            except Exception as src_e:
                logger.error(f"Error getting page source: {str(src_e)}")
                return ""
            
        except Exception as e:
            logger.error(f"Error fetching with Selenium: {str(e)}", exc_info=True)
            return ""
    
    async def _extract_hot_news_from_html(self, html_content: str) -> List[NewsItemModel]:
        """
        从HTML内容中提取热榜数据
        """
        if not html_content:
            logger.error("Empty HTML content")
            return []
        
        try:
            logger.info("Parsing HTML content with BeautifulSoup")
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 尝试不同的选择器查找热榜容器
            hot_news_containers = [
                # 专门处理"热榜"或"排行"相关的容器
                soup.find('div', class_=lambda c: c and 'report' in c),
                soup.find('div', class_=lambda c: c and 'rank' in c),
                soup.find('div', class_=lambda c: c and 'hot' in c),
                soup.find('div', class_=lambda c: c and 'list' in c and 'hot' in c),
                
                # 基于标题或内容查找
                soup.find('div', string=lambda s: s and ('热榜' in s or '排行' in s or '热点' in s)),
                soup.find('h2', string=lambda s: s and ('热榜' in s or '排行' in s or '热点' in s)),
                
                # 使用CSS选择器查找
                soup.select_one('div.index_ppreport__slNZB'),
                soup.select_one('div[class*="ppreport"]'),
                soup.select_one('div[class*="hot"]'),
                soup.select_one('div[class*="rank"]'),
                
                # 查找列表容器
                soup.select_one('div.index_content___Uhtm'),
                soup.select_one('div.mdContentBox'),
                soup.select_one('div.content-box'),
                
                # 从顶层开始寻找具有卡片格式的容器
                soup.find('div', class_=lambda c: c and ('card' in c.lower() or 'list' in c.lower())),
                soup.select_one('div[class*="card"]'),
                soup.select_one('div[class*="list"]'),
                
                # 寻找热榜专题区域
                soup.find('div', id=lambda i: i and ('hot' in i or 'rank' in i)),
                
                # 最后的备选：寻找含有多个li元素的ul
                next((
                    container.parent 
                    for container in soup.find_all('ul') 
                    if len(container.find_all('li')) > 5
                ), None)
            ]
            
            # 过滤None值
            hot_news_containers = [container for container in hot_news_containers if container]
            
            if not hot_news_containers:
                logger.error("No hot news containers found with any selector")
                
                # 尝试从页面中找到任何包含多个列表项的ul元素
                logger.info("Attempting to find any UL element with multiple LI children")
                ul_elements = soup.find_all('ul')
                ul_with_items = [(ul, len(ul.find_all('li'))) for ul in ul_elements]
                ul_with_items.sort(key=lambda x: x[1], reverse=True)
                
                if ul_with_items and ul_with_items[0][1] >= 3:
                    logger.info(f"Found UL element with {ul_with_items[0][1]} LI elements")
                    hot_news_container = ul_with_items[0][0]
                else:
                    logger.error("Could not find any suitable container")
                    # 保存失败页面以便调试
                    debug_file = self.config.get("failed_debug_file", "thepaper_failed_parse.html")
                    if debug_file:
                        try:
                            with open(debug_file, 'w', encoding='utf-8') as f:
                                f.write(html_content)
                            logger.info(f"Saved failed content to debug file: {debug_file}")
                        except Exception as e:
                            logger.error(f"Error saving failed debug file: {str(e)}")
                    return []
            else:
                logger.info(f"Found {len(hot_news_containers)} potential hot news containers")
                
                # 使用第一个找到的容器
                hot_news_container = hot_news_containers[0]
                logger.info(f"Using container: {hot_news_container.name}.{hot_news_container.get('class', '')}")
            
            # 查找内容区域（可能包含在容器内部或直接就是容器本身）
            content_containers = [
                # 在容器内查找内容区域
                hot_news_container.find('div', class_=lambda c: c and 'content' in c),
                hot_news_container.select_one('div[class*="content"]'),
                
                # 在容器内查找列表区域
                hot_news_container.find('div', class_=lambda c: c and ('list' in c or 'items' in c)),
                hot_news_container.select_one('div.list'),
                hot_news_container.select_one('div[class*="list"]'),
                
                # 容器本身可能就是内容区域
                hot_news_container
            ]
            
            # 过滤None值
            content_containers = [container for container in content_containers if container]
            
            if not content_containers:
                logger.error("Could not find content area in hot news container")
                return []
            
            # 使用第一个找到的内容区域
            content_div = content_containers[0]
            logger.info(f"Using content div: {content_div.name}.{content_div.get('class', '')}")
            
            # 查找ul元素 - 可能直接在内容区域或需要进一步查找
            ul_elements = [
                content_div.find('ul'),
                content_div.select_one('ul'),
                # 如果内容区域本身就是ul
                content_div if content_div.name == 'ul' else None
            ]
            
            # 过滤None值
            ul_elements = [ul for ul in ul_elements if ul]
            
            if not ul_elements:
                logger.warning("No UL element found in content div, searching for list items directly")
                
                # 直接查找li元素，无论是否在ul中
                li_elements = content_div.find_all('li')
                
                # 如果找不到li元素，尝试查找卡片元素
                if not li_elements:
                    logger.warning("No LI elements found, searching for card or item elements")
                    
                    # 查找可能的卡片元素
                    card_elements = content_div.find_all('div', class_=lambda c: c and ('card' in c.lower() or 'item' in c.lower()))
                    if card_elements:
                        logger.info(f"Found {len(card_elements)} card/item elements")
                        li_elements = card_elements
                    else:
                        # 最后的尝试：找到任何看起来像列表项的内容
                        logger.warning("No card elements found, searching for any div with links")
                        link_containers = content_div.find_all('div', lambda d: d.find('a'))
                        if link_containers:
                            logger.info(f"Found {len(link_containers)} divs containing links")
                            li_elements = link_containers
                        else:
                            logger.error("No suitable list items found in content div")
                            return []
            else:
                # 使用第一个找到的ul元素
                ul_element = ul_elements[0]
                logger.info(f"Found UL element: {ul_element.name}.{ul_element.get('class', '')}")
                
                # 查找所有li元素
                li_elements = ul_element.find_all('li')
            
            if not li_elements:
                logger.error("No LI elements found in UL or content area")
                logger.debug(f"UL/Content element HTML: {content_div}")
                return []
            
            logger.info(f"Found {len(li_elements)} hot news items")
            
            items = []
            for index, li in enumerate(li_elements):
                try:
                    # 查找卡片元素 - 可能是li本身或其内部的div
                    card_candidates = [
                        li.find('div', class_=lambda c: c and ('Card' in c or 'card' in c or 'item' in c)),
                        li.select_one('div[class*="Card"], div[class*="card"], div[class*="item"]'),
                        li  # li本身可能就是卡片
                    ]
                    
                    # 过滤None值
                    card_candidates = [card for card in card_candidates if card]
                    
                    if not card_candidates:
                        logger.warning(f"No card found in li element at index {index}")
                        continue
                    
                    card = card_candidates[0]
                    
                    # 获取排名
                    rank_element = card.find('i') or card.find('span', class_=lambda c: c and ('rank' in c.lower() or 'index' in c.lower() or 'num' in c.lower()))
                    rank = index + 1  # 默认使用索引+1作为排名
                    if rank_element:
                        try:
                            rank_text = rank_element.text.strip()
                            if rank_text.isdigit():
                                rank = int(rank_text)
                        except (ValueError, AttributeError):
                            logger.warning(f"Failed to parse rank from {rank_element}")
                    
                    # 获取链接元素
                    link_candidates = [
                        card.find('a'),
                        card.select_one('a')
                    ]
                    
                    # 过滤None值
                    link_candidates = [link for link in link_candidates if link]
                    
                    if not link_candidates:
                        logger.warning(f"Link element not found in card at index {index}")
                        # 尝试查找任何带有href属性的元素
                        elements_with_href = card.find_all(lambda tag: tag.has_attr('href'))
                        if elements_with_href:
                            link_element = elements_with_href[0]
                        else:
                            logger.warning(f"No elements with href found at index {index}")
                            continue
                    else:
                        link_element = link_candidates[0]
                    
                    # 获取URL
                    url = link_element.get('href', '')
                    if url and not url.startswith('http'):
                        url = f"https://www.thepaper.cn{url}"
                    
                    if not url:
                        logger.warning(f"No URL found for item at index {index}")
                        continue
                    
                    # 获取标题
                    title_candidates = [
                        link_element.find('h2'),
                        link_element.select_one('h2'),
                        link_element.find('h3'),
                        link_element.select_one('h3'),
                        link_element.find('h4'),
                        link_element.select_one('h4'),
                        link_element.find('div', class_=lambda c: c and ('title' in c.lower() or 'header' in c.lower())),
                        link_element.select_one('div[class*="title"], div[class*="header"]'),
                        link_element.find('span', class_=lambda c: c and ('title' in c.lower() or 'text' in c.lower())),
                        link_element.select_one('span[class*="title"], span[class*="text"]'),
                        link_element  # 如果没有特定的标题元素，直接使用链接元素
                    ]
                    
                    # 过滤None值
                    title_candidates = [title for title in title_candidates if title]
                    
                    if not title_candidates:
                        logger.warning(f"No title element found for item at index {index}")
                        continue
                    
                    title_element = title_candidates[0]
                    title = title_element.get_text(strip=True)
                    
                    if not title:
                        logger.warning(f"No title text found for item at index {index}")
                        continue
                    
                    # 获取摘要（如果有）
                    summary_candidates = [
                        link_element.find('p'),
                        link_element.select_one('p'),
                        link_element.find('div', class_=lambda c: c and ('desc' in c.lower() or 'summary' in c.lower() or 'content' in c.lower())),
                        link_element.select_one('div[class*="desc"], div[class*="summary"], div[class*="content"]'),
                        card.find('p'),
                        card.select_one('p')
                    ]
                    
                    # 过滤None值
                    summary_candidates = [summary for summary in summary_candidates if summary]
                    
                    summary = ""
                    if summary_candidates:
                        summary_element = summary_candidates[0]
                        summary = summary_element.get_text(strip=True)
                    
                    # 获取图片URL（如果有）
                    image_url = ""
                    img_candidates = [
                        link_element.find('img'),
                        link_element.select_one('img'),
                        card.find('img'),
                        card.select_one('img')
                    ]
                    
                    # 过滤None值
                    img_candidates = [img for img in img_candidates if img]
                    
                    if img_candidates:
                        img_element = img_candidates[0]
                        image_url = img_element.get('src', '') or img_element.get('data-src', '')
                        if image_url and not image_url.startswith('http'):
                            image_url = f"https:{image_url}" if image_url.startswith('//') else f"https://www.thepaper.cn{image_url}"
                    
                    # 获取热度（如果有）
                    hot_candidates = [
                        card.find('span', class_=lambda c: c and ('hot' in c.lower() or 'count' in c.lower() or 'view' in c.lower())),
                        card.select_one('span[class*="hot"], span[class*="count"], span[class*="view"]'),
                        card.find('div', class_=lambda c: c and ('hot' in c.lower() or 'count' in c.lower() or 'view' in c.lower())),
                        card.select_one('div[class*="hot"], div[class*="count"], div[class*="view"]')
                    ]
                    
                    # 过滤None值
                    hot_candidates = [hot for hot in hot_candidates if hot]
                    
                    hot_value = ""
                    if hot_candidates:
                        hot_element = hot_candidates[0]
                        hot_value = hot_element.get_text(strip=True)
                    
                    # 生成唯一ID
                    news_id = hashlib.md5(f"{url}_{title}".encode()).hexdigest()
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=news_id,
                        title=title,
                        url=url,
                        content=summary,
                        summary=summary,
                        image_url=image_url,
                        published_at=datetime.datetime.now(datetime.timezone.utc),  # 使用当前时间
                        extra={
                            "rank": rank,
                            "hot": hot_value,
                            "source": "thepaper"
                        }
                    )
                    
                    items.append(news_item)
                    logger.debug(f"Processed item {rank}: {title}")
                    
                except Exception as e:
                    logger.error(f"Error processing hot news item at index {index}: {str(e)}", exc_info=True)
                    continue
            
            if not items:
                logger.error("No items could be extracted from the page")
            else:
                logger.info(f"Successfully extracted {len(items)} items")
            
            return items
            
        except Exception as e:
            logger.error(f"Error extracting hot news from HTML: {str(e)}", exc_info=True)
            return []
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        从澎湃新闻获取热榜数据
        修改策略：优先使用第三方API，如果API失败再尝试使用Selenium
        """
        logger.info(f"Fetching ThePaper hot news")
        
        # 优先尝试使用第三方API
        if self.config.get("use_api", True):
            try:
                logger.info("Attempting to fetch hot news from third-party API")
                items = await self._fetch_from_third_party_api()
                if items:
                    logger.info(f"Successfully fetched {len(items)} items from third-party API")
                    return items
                logger.warning("Failed to fetch data from third-party API, will try Selenium")
            except Exception as e:
                logger.error(f"Error fetching from third-party API: {str(e)}")
                logger.info("Will try Selenium as fallback")
        
        # 如果API获取失败，尝试使用Selenium
        if self.config.get("use_selenium", True):
            logger.info("Attempting to fetch hot news with Selenium")
            max_retries = self.config.get("max_retries", 3)
            retry_delay = self.config.get("retry_delay", 5)
            
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(f"Selenium attempt {attempt}/{max_retries}")
                    
                    html_content = await self._fetch_with_selenium()
                    if not html_content:
                        logger.warning(f"Empty content returned on Selenium attempt {attempt}")
                        if attempt < max_retries:
                            logger.info(f"Retrying in {retry_delay} seconds...")
                            await asyncio.sleep(retry_delay)
                        continue
                    
                    # 检查是否被拒绝访问（403）
                    if "<title>403 Forbidden</title>" in html_content:
                        logger.error("Access forbidden (403) by the website")
                        break  # 不再重试，因为IP可能已被封
                    
                    logger.info(f"Successfully fetched content with Selenium on attempt {attempt}")
                    
                    # 保存内容到调试文件（可选）
                    debug_file = self.config.get("debug_file", "")
                    if debug_file:
                        try:
                            with open(debug_file, 'w', encoding='utf-8') as f:
                                f.write(html_content)
                            logger.info(f"Saved content to debug file: {debug_file}")
                        except Exception as e:
                            logger.error(f"Error saving debug file: {str(e)}")
                    
                    # 从HTML中提取热榜数据
                    items = await self._extract_hot_news_from_html(html_content)
                    if items:
                        logger.info(f"Successfully extracted {len(items)} items from HTML")
                        return items
                    else:
                        logger.warning("Failed to extract hot news items from HTML")
                    
                    # 如果提取失败，尝试下一次获取
                    if attempt < max_retries:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                    
                except Exception as e:
                    logger.error(f"Error on Selenium attempt {attempt}: {str(e)}", exc_info=True)
                    if attempt < max_retries:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
        
        # 如果所有方法都失败，尝试最后一次从第三方API获取
        try:
            logger.info("All previous attempts failed, making final attempt with third-party API")
            items = await self._fetch_from_third_party_api()
            if items:
                logger.info(f"Final API attempt succeeded with {len(items)} items")
                return items
        except Exception as e:
            logger.error(f"Final API attempt failed: {str(e)}")
        
        logger.error("All methods failed to fetch ThePaper hot news")
        return []
    
    async def _fetch_from_third_party_api(self) -> List[NewsItemModel]:
        """
        从第三方API获取澎湃新闻热榜数据
        """
        try:
            # 从配置获取API URL
            api_url = self.config.get("api_url", self.THIRD_PARTY_API_URL)
            
            logger.info(f"Fetching hot news from API: {api_url}")
            
            # 随机用户代理
            user_agent = random.choice(self.USER_AGENTS)
            
            # 设置请求头
            headers = {
                "User-Agent": user_agent,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1"  # Do Not Track
            }
            
            # 从异步HTTP客户端获取数据
            timeout = self.config.get("api_timeout", 10)
            
            # 使用http_client.fetch而不是http_client.get
            data = await http_client.fetch(
                url=api_url,
                method="GET",
                headers=headers,
                response_type="json",
                timeout=timeout
            )
            
            # 检查返回的数据
            if not data:
                logger.error("Empty response from API")
                return []
                
            # 检查API返回格式
            if 'success' not in data or not data['success']:
                logger.error(f"API returned error: {data.get('message', 'Unknown error')}")
                return []
            
            # 获取热榜数据
            hot_news_data = data.get('data', [])
            
            if not hot_news_data:
                logger.error("No hot news data found in API response")
                return []
            
            logger.info(f"Found {len(hot_news_data)} items in API response")
            
            # 处理提取到的数据
            items = []
            for index, item_data in enumerate(hot_news_data):
                try:
                    # 提取标题和URL
                    title = item_data.get('title', '')
                    url = item_data.get('url', '')
                    
                    if not title or not url:
                        logger.warning(f"Missing title or URL in item {index}")
                        continue
                    
                    # 获取排名
                    rank = item_data.get('index', index + 1)
                    if not isinstance(rank, int):
                        try:
                            rank = int(rank)
                        except (ValueError, TypeError):
                            rank = index + 1
                    
                    # 获取热度
                    hot_value = item_data.get('hot', '')
                    
                    # 获取手机版URL（如果有）
                    mobile_url = item_data.get('mobil_url', '')
                    
                    # 生成唯一ID
                    news_id = hashlib.md5(f"{url}_{title}".encode()).hexdigest()
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=news_id,
                        title=title,
                        url=url,
                        summary="",  # API没有提供摘要
                        image_url="",  # API没有提供图片
                        published_at=datetime.datetime.now(datetime.timezone.utc),  # 使用当前时间
                        extra={
                            "rank": rank,
                            "hot": hot_value,
                            "mobile_url": mobile_url,
                            "source": "thepaper",
                            "source_from": "api"
                        }
                    )
                    
                    items.append(news_item)
                    logger.debug(f"Processed API item {rank}: {title}")
                except Exception as e:
                    logger.error(f"Error processing API item at index {index}: {str(e)}")
            
            # 保存API响应到调试文件（可选）
            debug_file = self.config.get("api_debug_file", "")
            if debug_file:
                try:
                    import json
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    logger.info(f"Saved API response to debug file: {debug_file}")
                except Exception as e:
                    logger.error(f"Error saving API debug file: {str(e)}")
            
            return items
        
        except Exception as e:
            logger.error(f"Error fetching from API: {str(e)}", exc_info=True)
            return []
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析HTTP响应内容
        注意：这个方法是必须的，因为它是从WebNewsSource继承的抽象方法
        """
        logger.info("Using parse_response method to process content")
        return await self._extract_hot_news_from_html(response) 