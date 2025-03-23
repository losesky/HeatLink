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
    # 备用API列表
    BACKUP_API_URLS = [
        "https://api.vvhan.com/api/hotlist/pengPai", 
        "https://api.oioweb.cn/api/news/thepaper"
    ]
    
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
            "use_api": False,  # 默认禁用API
            "api_url": self.THIRD_PARTY_API_URL,
            "api_timeout": 10,  # API请求超时时间（秒）
            # Selenium配置
            "use_selenium": True,  # 默认启用Selenium
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
            # 调试配置
            "debug_file": "/tmp/thepaper_selenium_debug.html",  # 调试文件路径
            "failed_debug_file": "/tmp/thepaper_selenium_failed.html",  # 失败时的调试文件路径
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
        self._driver_pid = None  # 添加记录chromedriver进程ID
        logger.info(f"初始化 {self.name} 适配器，URL: {self.url}，启用Selenium: {self.config.get('use_selenium', True)}，无头模式: {self.config.get('headless', True)}")
        
        # 设置API URL
        self.api_url = config.get("api_url", self.THIRD_PARTY_API_URL)
        logger.info(f"使用API URL: {self.api_url}")
    
    def _create_driver(self):
        """
        创建并配置Selenium WebDriver
        """
        try:
            logger.debug("开始创建Chrome WebDriver实例")
            chrome_options = Options()
            
            # 设置无头模式（不显示浏览器窗口）
            if self.config.get("headless", False):
                logger.debug("启用无头模式")
                chrome_options.add_argument("--headless=new")  # 使用新的无头模式
            
            # 设置用户代理
            user_agent = random.choice(self.USER_AGENTS)
            logger.debug(f"使用用户代理: {user_agent}")
            chrome_options.add_argument(f"--user-agent={user_agent}")
            
            # 禁用GPU加速（在无头模式下可能导致问题）
            chrome_options.add_argument("--disable-gpu")
            
            # 禁用扩展
            chrome_options.add_argument("--disable-extensions")
            
            # 禁用沙盒（在Docker容器中可能需要）
            chrome_options.add_argument("--no-sandbox")
            
            # 禁用开发者工具
            chrome_options.add_argument("--disable-dev-shm-usage")

            # 增加内存限制
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--memory-pressure-off")
            chrome_options.add_argument("--disable-features=MemoryPressureHandling")
            
            # 关闭某些可能导致问题的功能
            chrome_options.add_argument("--disable-web-security")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-popup-blocking")
            chrome_options.add_argument("--ignore-certificate-errors")
            
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
                logger.info("正在使用webdriver-manager下载匹配的ChromeDriver")
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("成功使用webdriver-manager创建ChromeDriver")
            except Exception as e:
                logger.warning(f"使用webdriver-manager失败: {str(e)}")
                # 尝试使用系统路径
                logger.info("尝试使用系统ChromeDriver路径")
                system = platform.system()
                if system == "Windows":
                    executable_path = './resource/chromedriver.exe'
                    logger.debug(f"Windows系统，使用路径: {executable_path}")
                elif system == "Linux":
                    # 尝试多个可能的路径
                    possible_paths = [
                        '/usr/bin/chromedriver',
                        '/usr/local/bin/chromedriver',
                        '/snap/bin/chromedriver'
                    ]
                    executable_path = None
                    for path in possible_paths:
                        logger.debug(f"检查Linux ChromeDriver路径: {path}")
                        if os.path.exists(path):
                            executable_path = path
                            logger.debug(f"找到可用的ChromeDriver路径: {path}")
                            break
                    if not executable_path:
                        logger.error("在常见Linux路径中未找到ChromeDriver")
                        raise Exception("ChromeDriver not found in common Linux paths")
                else:
                    logger.error(f"不支持的系统: {system}")
                    raise Exception("Unsupported system detected")
                
                logger.info(f"使用ChromeDriver路径: {executable_path}")
                service = Service(executable_path=executable_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("成功使用系统路径创建ChromeDriver")
            
            # 设置页面加载超时
            driver.set_page_load_timeout(self.config.get("selenium_timeout", 30))
            
            # 设置脚本执行超时
            driver.set_script_timeout(self.config.get("selenium_timeout", 30))
            
            logger.info("成功创建Chrome WebDriver")
            
            # 记录driver进程ID，用于后续清理
            try:
                self._driver_pid = driver.service.process.pid
                logger.info(f"ChromeDriver进程ID: {self._driver_pid}")
            except Exception as pid_e:
                logger.warning(f"无法获取ChromeDriver PID: {str(pid_e)}")
                
            return driver
            
        except Exception as e:
            logger.error(f"创建Chrome WebDriver时出错: {str(e)}", exc_info=True)
            return None
    
    async def _get_driver(self):
        """
        获取WebDriver实例，如果不存在则创建
        """
        if self._driver is None:
            logger.info("WebDriver不存在，开始创建新的WebDriver实例")
            # 在事件循环中运行阻塞的WebDriver创建
            loop = asyncio.get_event_loop()
            self._driver = await loop.run_in_executor(None, self._create_driver)
            if self._driver:
                logger.info("成功创建并获取WebDriver实例")
            else:
                logger.error("创建WebDriver实例失败")
        else:
            logger.debug("重用现有WebDriver实例")
        return self._driver
    
    async def _close_driver(self):
        """
        关闭WebDriver及其相关进程
        """
        if self._driver is not None:
            try:
                logger.info("Closing Chrome WebDriver")
                loop = asyncio.get_event_loop()
                
                # 首先尝试正常关闭
                try:
                    await loop.run_in_executor(None, self._driver.quit)
                    logger.info("Successfully closed Chrome WebDriver")
                except Exception as e:
                    logger.error(f"Error closing Chrome WebDriver normally: {str(e)}", exc_info=True)
                    
                    # 如果正常关闭失败，尝试强制关闭
                    try:
                        # 记录关联的Chrome进程
                        chrome_processes = []
                        if hasattr(self._driver, 'service') and hasattr(self._driver.service, 'process'):
                            chrome_processes.append(self._driver.service.process)
                        
                        # 如果有记录进程ID，直接使用psutil强制终止
                        if self._driver_pid:
                            try:
                                import psutil
                                driver_process = psutil.Process(self._driver_pid)
                                children = driver_process.children(recursive=True)
                                
                                # 先终止子进程
                                for child in children:
                                    try:
                                        child.terminate()
                                        logger.info(f"Terminated child process PID: {child.pid}")
                                    except:
                                        try:
                                            child.kill()
                                            logger.info(f"Killed child process PID: {child.pid}")
                                        except:
                                            pass
                                
                                # 然后终止driver进程
                                driver_process.terminate()
                                logger.info(f"Terminated ChromeDriver process PID: {self._driver_pid}")
                            except Exception as kill_e:
                                logger.error(f"Failed to kill ChromeDriver process: {str(kill_e)}")
                    except Exception as force_e:
                        logger.error(f"Error force closing Chrome processes: {str(force_e)}")
            finally:
                self._driver = None
                self._driver_pid = None
    
    async def close(self):
        """
        关闭资源
        """
        await self._close_driver()
        await super().close()
    
    async def _fetch_with_selenium(self) -> List[NewsItemModel]:
        """
        使用Selenium从澎湃新闻获取数据
        
        过程中直接收集新闻内容，减少中间转换步骤
        """
        logger.info("开始使用Selenium获取澎湃新闻数据")
        driver = await self._get_driver()
        if driver is None:
            logger.error("未能创建WebDriver，无法使用Selenium获取内容")
            raise RuntimeError("无法获取澎湃新闻数据：WebDriver创建失败")
        
        news_items = []
        try:
            # 随机延迟，模拟人类行为
            if self.config.get("use_random_delay", True):
                delay = random.uniform(
                    self.config.get("min_delay", 1.0),
                    self.config.get("max_delay", 3.0)
                )
                logger.debug(f"请求前随机延迟: {delay:.2f} 秒")
                await asyncio.sleep(delay)
            
            # 访问页面
            logger.info(f"正在打开URL: {self.url}")
            loop = asyncio.get_event_loop()
            
            # 使用超时控制
            try:
                page_load_timeout = self.config.get("selenium_timeout", 30)
                logger.info(f"设置页面加载超时为 {page_load_timeout} 秒")
                
                # 设置超时
                await loop.run_in_executor(
                    None, 
                    lambda: driver.set_page_load_timeout(page_load_timeout)
                )
                
                # 访问URL
                start_time = time.time()
                await loop.run_in_executor(None, lambda: driver.get(self.url))
                end_time = time.time()
                logger.info(f"成功导航到URL，耗时 {end_time - start_time:.2f} 秒")
            except Exception as e:
                logger.error(f"加载页面时出错: {str(e)}")
                
                # 尝试使用JavaScript导航（可能绕过某些超时问题）
                try:
                    logger.info("尝试使用JavaScript导航")
                    await loop.run_in_executor(
                        None,
                        lambda: driver.execute_script(f"window.location.href = '{self.url}';")
                    )
                    
                    # 等待页面加载
                    await asyncio.sleep(10)
                    logger.info("成功使用JavaScript导航")
                except Exception as js_e:
                    logger.error(f"使用JavaScript导航时出错: {str(js_e)}")
                    raise RuntimeError(f"无法获取澎湃新闻数据：页面加载失败 - {str(js_e)}")
            
            # 等待页面加载完成
            logger.info("等待页面加载完成")
            await asyncio.sleep(5)
            
            # 直接尝试获取新闻列表
            try:
                # 尝试获取页面上的所有新闻项
                logger.info("尝试直接从页面提取新闻列表")
                news_elements = []
                
                # 尝试不同的选择器找到新闻列表项
                selectors = [
                    "div.index_ppreport__slNZB a", 
                    ".mdCard a",
                    "ul a.index_inherit__A1ImK", 
                    ".home_wrapper__H8fk4 a",
                    ".content a",
                    "div[class*=cardBox] a",
                    "a[href*=newsDetail]"  # 查找链接到新闻详情的a标签
                ]
                
                for selector in selectors:
                    try:
                        logger.info(f"尝试选择器: {selector}")
                        elements = await loop.run_in_executor(
                            None, 
                            lambda: driver.find_elements(By.CSS_SELECTOR, selector)
                        )
                        if elements and len(elements) >= 3:  # 至少找到3个元素才算有效
                            logger.info(f"使用选择器 {selector} 找到 {len(elements)} 个元素")
                            news_elements = elements
                            break
                    except Exception as elem_e:
                        logger.warning(f"使用选择器 {selector} 查找元素时出错: {str(elem_e)}")
                
                if not news_elements:
                    logger.warning("没有找到新闻元素，尝试截图以供分析")
                    try:
                        screenshot_path = "/tmp/thepaper_debug_screenshot.png"
                        await loop.run_in_executor(
                            None,
                            lambda: driver.save_screenshot(screenshot_path)
                        )
                        logger.info(f"保存截图到 {screenshot_path}")
                    except Exception as ss_e:
                        logger.error(f"保存截图时出错: {str(ss_e)}")
                    
                    raise RuntimeError("无法获取澎湃新闻数据：未找到新闻元素")
                
                # 提取新闻数据
                logger.info(f"开始从 {len(news_elements)} 个元素中提取新闻数据")
                for index, element in enumerate(news_elements[:30]):  # 最多处理前30个
                    try:
                        # 获取链接
                        url = await loop.run_in_executor(
                            None,
                            lambda: element.get_attribute('href')
                        )
                        
                        # 获取标题
                        title = await loop.run_in_executor(
                            None,
                            lambda: element.text.strip()
                        )
                        
                        # 如果没有标题文本，尝试获取title属性
                        if not title:
                            title = await loop.run_in_executor(
                                None,
                                lambda: element.get_attribute('title')
                            )
                        
                        # 确保URL和标题不为空
                        if not url or not title:
                            logger.warning(f"元素 {index} 缺少URL或标题: URL={url}, 标题={title}")
                            continue
                        
                        # 确保URL以http开头
                        if not url.startswith('http'):
                            url = f"https://www.thepaper.cn{url}"
                        
                        # 生成唯一ID
                        news_id = hashlib.md5(f"{url}_{title}".encode()).hexdigest()
                        
                        # 创建新闻项
                        news_item = self.create_news_item(
                            id=news_id,
                            title=title,
                            url=url,
                            summary="",  # 没有摘要
                            image_url="",  # 没有图片URL
                            published_at=datetime.datetime.now(datetime.timezone.utc),  # 使用当前时间
                            extra={
                                "rank": index + 1,
                                "source": "thepaper",
                                "source_from": "selenium"
                            }
                        )
                        
                        news_items.append(news_item)
                        logger.debug(f"提取到新闻项 {index + 1}: {title}")
                    except Exception as item_e:
                        logger.error(f"处理元素 {index} 时出错: {str(item_e)}")
                
                logger.info(f"成功提取到 {len(news_items)} 个新闻项")
                if not news_items:
                    logger.warning("没有提取到新闻，返回模拟数据")
                    return self._create_mock_data()
                
                return news_items
                
            except Exception as extract_e:
                logger.error(f"提取新闻列表时出错: {str(extract_e)}")
                raise RuntimeError(f"提取新闻列表时出错: {str(extract_e)}")
                
        except Exception as e:
            logger.error(f"使用Selenium获取内容时出错: {str(e)}", exc_info=True)
            raise RuntimeError(f"使用Selenium获取内容时出错: {str(e)}")
        finally:
            # 确保关闭driver
            await self._close_driver()

    async def fetch(self) -> List[NewsItemModel]:
        """
        获取澎湃新闻热榜
        
        Returns:
            新闻列表
        """
        logger.info("Fetching ThePaper hot news")
        news_items = []
        
        # 强制不使用API获取数据
        try:
            # 直接使用Selenium
            logger.info("配置禁用API，直接使用Selenium获取")
            if self.config.get("use_selenium", True):
                try:
                    news_items = await self._fetch_with_selenium()
                    if news_items:
                        logger.info(f"成功使用Selenium获取到 {len(news_items)} 条新闻")
                except Exception as se_e:
                    logger.error(f"使用Selenium获取数据失败: {str(se_e)}", exc_info=True)
            else:
                logger.error("Selenium未启用，无法获取数据")
                raise RuntimeError("Selenium未启用，无法获取数据")
            
            # 如果没有获取到数据，抛出异常
            if not news_items:
                logger.error("Selenium获取失败，无法获取澎湃新闻数据")
                raise RuntimeError("无法获取澎湃新闻数据：Selenium获取失败")
            
            return news_items
        finally:
            # 确保每次fetch后都关闭driver，防止资源泄漏
            try:
                await self._close_driver()
            except Exception as close_e:
                logger.error(f"关闭WebDriver时出错: {str(close_e)}")

    def _create_mock_data(self) -> List[NewsItemModel]:
        """
        生成模拟澎湃新闻数据
        """
        news_items = []
        current_time = datetime.datetime.now()
        
        # 生成模拟新闻
        mock_news = [
            {
                "title": "国务院：加大对民营经济政策支持力度",
                "url": "https://www.thepaper.cn/newsDetail_forward_123456",
                "rank": 1
            },
            {
                "title": "中共中央政治局召开会议，研究部署经济工作",
                "url": "https://www.thepaper.cn/newsDetail_forward_234567",
                "rank": 2
            },
            {
                "title": "多部门联合发布数字经济发展新规划",
                "url": "https://www.thepaper.cn/newsDetail_forward_345678",
                "rank": 3
            },
            {
                "title": "全国人大常委会审议多项法律草案",
                "url": "https://www.thepaper.cn/newsDetail_forward_456789",
                "rank": 4
            },
            {
                "title": "教育部：进一步规范校外培训机构",
                "url": "https://www.thepaper.cn/newsDetail_forward_567890",
                "rank": 5
            },
            {
                "title": "北京冬奥会筹备工作进入最后阶段",
                "url": "https://www.thepaper.cn/newsDetail_forward_678901",
                "rank": 6
            },
            {
                "title": "上海进一步优化营商环境，出台新政策",
                "url": "https://www.thepaper.cn/newsDetail_forward_789012",
                "rank": 7
            },
            {
                "title": "世卫组织：全球新冠疫情呈现新特点",
                "url": "https://www.thepaper.cn/newsDetail_forward_890123",
                "rank": 8
            }
        ]
        
        # 创建新闻项
        for item in mock_news:
            news_id = hashlib.md5(f"{item['url']}_{item['title']}".encode()).hexdigest()
            
            news_item = self.create_news_item(
                id=news_id,
                title=item["title"],
                url=item["url"],
                summary="(模拟数据)",
                published_at=current_time - datetime.timedelta(hours=random.randint(1, 12)),
                extra={
                    "rank": item["rank"],
                    "is_mock": True,
                    "source": "澎湃新闻(模拟数据)"
                }
            )
            
            news_items.append(news_item)
        
        logger.info(f"Created {len(news_items)} mock ThePaper news items")
        return news_items
    
    async def _fetch_from_api(self, api_url: str) -> List[NewsItemModel]:
        """
        从第三方API获取澎湃新闻热榜数据
        """
        try:
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