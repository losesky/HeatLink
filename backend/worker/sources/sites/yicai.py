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
import aiohttp

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

# 创建日志记录器
logger = logging.getLogger(__name__)
# 设置日志级别
logger.setLevel(logging.INFO)

# 全局调试模式标志
DEBUG_MODE = False

class YiCaiBaseSource(WebNewsSource):
    """
    第一财经新闻适配器基类 - Selenium版本
    可以获取第一财经网站的快讯和新闻内容
    
    特性:
    - 使用Selenium从网站获取新闻数据
    - 支持获取快讯和新闻两个板块的内容
    - 使用缓存机制减少请求频率
    - 提供HTTP备用方案，确保高可用性
    """
    
    # 用户代理列表
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Edge/120.0.0.0"
    ]
    
    # URL常量
    BRIEF_URL = "https://www.yicai.com/brief/"
    NEWS_URL = "https://www.yicai.com/news/"
    
    def __init__(
        self,
        source_id: str,
        name: str,
        url: str = "https://www.yicai.com/",
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "finance",
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
            },
            # Selenium配置
            "use_selenium": True,  # 启用Selenium
            "selenium_timeout": 15,  # 页面加载超时时间（秒）
            "selenium_wait_time": 3,  # 等待元素出现的时间（秒）
            "headless": True,  # 无头模式
            # 重试配置
            "max_retries": 2,
            "retry_delay": 2,
            # 启用缓存
            "use_cache": True,
            "cache_ttl": 1800,  # 30分钟缓存
            # 启用随机延迟
            "use_random_delay": True,
            "min_delay": 0.5,
            "max_delay": 1.5,
            # 整体超时控制
            "overall_timeout": 60,  # 整体操作超时时间（秒）
            # HTTP备用方式
            "use_http_fallback": True,
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
        self._driver_pid = None
        
        # 缓存相关
        self._news_cache = []
        self._last_cache_update = 0
        self._cache_ttl = 1800  # 30分钟缓存有效期
        self._cache_lock = asyncio.Lock()
        
        # HTTP备用标志
        self._tried_http_fallback = False

    def _create_driver(self):
        """
        创建并配置Selenium WebDriver
        """
        try:
            logger.debug("开始创建Chrome WebDriver实例")
            chrome_options = Options()
            
            # 设置无头模式
            if self.config.get("headless", False):
                logger.debug("启用无头模式")
                chrome_options.add_argument("--headless=new")
            
            # 设置用户代理
            user_agent = random.choice(self.USER_AGENTS)
            logger.debug(f"使用用户代理: {user_agent}")
            chrome_options.add_argument(f"--user-agent={user_agent}")
            
            # 设置窗口大小
            chrome_options.add_argument("--window-size=1920,1080")
            
            # 禁用GPU加速
            chrome_options.add_argument("--disable-gpu")
            
            # 禁用扩展
            chrome_options.add_argument("--disable-extensions")
            
            # 禁用沙盒
            chrome_options.add_argument("--no-sandbox")
            
            # 禁用开发者工具
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            # 禁用自动化控制提示
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            
            # 启用JavaScript
            chrome_options.add_argument("--enable-javascript")
            
            # 设置语言
            chrome_options.add_argument("--lang=zh-CN")
            
            # 尝试使用系统的ChromeDriver
            try:
                # 定义可能的ChromeDriver路径
                system = platform.system()
                logger.info(f"当前系统: {system}")
                
                if system == "Windows":
                    chromedriver_paths = [
                        './resource/chromedriver.exe',
                        'C:\\Program Files\\Google\\Chrome\\Application\\chromedriver.exe',
                        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chromedriver.exe'
                    ]
                elif system == "Linux":
                    chromedriver_paths = [
                        '/usr/local/bin/chromedriver',
                        '/usr/bin/chromedriver',
                        '/snap/bin/chromedriver',
                        '/home/losesky/HeatLink/chromedriver'
                    ]
                else:  # macOS or other
                    chromedriver_paths = [
                        '/usr/local/bin/chromedriver',
                        '/usr/bin/chromedriver'
                    ]
                
                # 查找第一个存在的ChromeDriver路径
                chromedriver_path = None
                for path in chromedriver_paths:
                    if os.path.exists(path):
                        chromedriver_path = path
                        logger.info(f"找到ChromeDriver路径: {path}")
                        break
                
                if not chromedriver_path:
                    # 如果没有找到，尝试直接使用默认的 'chromedriver'
                    chromedriver_path = "chromedriver"
                    logger.info("使用系统PATH中的ChromeDriver")
                
                # 创建服务和WebDriver
                service = Service(executable_path=chromedriver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("成功创建Chrome WebDriver实例")
                
                # 记录driver进程ID
                try:
                    self._driver_pid = driver.service.process.pid
                    logger.info(f"ChromeDriver进程ID: {self._driver_pid}")
                except Exception as pid_e:
                    logger.warning(f"无法获取ChromeDriver PID: {str(pid_e)}")
                
                # 设置页面加载超时
                driver.set_page_load_timeout(self.config.get("selenium_timeout", 30))
                
                # 设置脚本执行超时
                driver.set_script_timeout(self.config.get("selenium_timeout", 30))
                
                return driver
                
            except Exception as driver_e:
                logger.error(f"使用系统ChromeDriver失败: {str(driver_e)}")
                
                # 尝试使用webdriver_manager作为最后的手段
                try:
                    logger.info("尝试使用webdriver_manager...")
                    
                    service = Service(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                    logger.info("成功使用webdriver_manager创建WebDriver实例")
                    
                    # 设置页面加载超时和脚本执行超时
                    driver.set_page_load_timeout(self.config.get("selenium_timeout", 30))
                    driver.set_script_timeout(self.config.get("selenium_timeout", 30))
                    
                    return driver
                    
                except Exception as wdm_e:
                    logger.error(f"使用webdriver_manager失败: {str(wdm_e)}")
                
                raise Exception("无法创建Chrome WebDriver: 所有方法都失败")
                
        except Exception as e:
            logger.error(f"创建Chrome WebDriver时出错: {str(e)}")
            return None
    
    async def _get_driver(self):
        """
        获取WebDriver实例，如果不存在则创建
        """
        if self._driver is None:
            if DEBUG_MODE:
                logger.debug("创建新的WebDriver实例")
            # 在事件循环中运行阻塞的WebDriver创建
            loop = asyncio.get_event_loop()
            self._driver = await loop.run_in_executor(None, self._create_driver)
            if not self._driver:
                logger.error("WebDriver创建失败")
        
        return self._driver
    
    async def _close_driver(self):
        """
        关闭WebDriver及其相关进程
        """
        if self._driver is not None:
            try:
                if DEBUG_MODE:
                    logger.debug("正在关闭WebDriver")
                loop = asyncio.get_event_loop()
                
                # 首先尝试正常关闭
                try:
                    await loop.run_in_executor(None, self._driver.quit)
                    if DEBUG_MODE:
                        logger.debug("WebDriver已关闭")
                except Exception as e:
                    if DEBUG_MODE:
                        logger.debug(f"正常关闭WebDriver失败: {str(e)}")
                    
                    # 如果正常关闭失败，尝试强制关闭
                    try:
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
                                    except:
                                        try:
                                            child.kill()
                                        except:
                                            pass
                                
                                # 然后终止driver进程
                                driver_process.terminate()
                                if DEBUG_MODE:
                                    logger.debug(f"强制终止WebDriver进程 (PID: {self._driver_pid})")
                            except Exception:
                                pass
                    except Exception:
                        pass
            finally:
                self._driver = None
                self._driver_pid = None 

    async def fetch(self) -> List[NewsItemModel]:
        """
        获取第一财经新闻和快讯
        同时抓取两个板块的内容并合并
        """
        logger.info(f"开始获取第一财经数据")
        start_time = time.time()
        
        # 首先检查缓存是否有效
        current_time = time.time()
        if self._news_cache and current_time - self._last_cache_update < self._cache_ttl:
            logger.info(f"从缓存获取到 {len(self._news_cache)} 条第一财经数据，用时: {time.time() - start_time:.2f}秒")
            return self._news_cache.copy()
        
        # 设置整体超时
        overall_timeout = self.config.get("overall_timeout", 60)
        
        # 创建异步任务
        try:
            # 创建异步任务
            fetch_task = asyncio.create_task(self._fetch_impl())
            
            # 使用超时控制
            try:
                news_items = await asyncio.wait_for(fetch_task, timeout=overall_timeout)
                
                # 记录执行时间
                elapsed = time.time() - start_time
                logger.info(f"成功获取 {len(news_items)} 条第一财经数据，用时: {elapsed:.2f}秒")
                
                # 更新缓存
                async with self._cache_lock:
                    self._news_cache = news_items
                    self._last_cache_update = time.time()
                
                return news_items
            except asyncio.TimeoutError:
                logger.warning(f"获取第一财经数据超时 ({overall_timeout}秒)，尝试使用备用方法")
                
                # 如果使用Selenium超时，尝试HTTP备用方法
                if self.config.get("use_http_fallback", True) and not self._tried_http_fallback:
                    logger.info("尝试使用HTTP备用方法获取数据")
                    self._tried_http_fallback = True
                    try:
                        fallback_items = await self._fetch_with_http_fallback()
                        if fallback_items:
                            # 更新缓存
                            async with self._cache_lock:
                                self._news_cache = fallback_items
                                self._last_cache_update = time.time()
                            
                            elapsed = time.time() - start_time
                            logger.info(f"通过HTTP备用方法成功获取 {len(fallback_items)} 条新闻，总用时: {elapsed:.2f}秒")
                            
                            return fallback_items
                    except Exception as fallback_e:
                        logger.error(f"HTTP备用方法失败: {str(fallback_e)}")
                
                # 如果有缓存，返回缓存
                if self._news_cache:
                    logger.info(f"返回缓存的 {len(self._news_cache)} 条新闻")
                    return self._news_cache.copy()
                
                logger.error("获取第一财经数据完全失败")
                return []
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"获取第一财经数据时发生错误: {str(e)}，用时: {elapsed:.2f}秒")
            
            # 如果有缓存，返回缓存
            if self._news_cache:
                logger.info(f"错误后返回缓存的 {len(self._news_cache)} 条新闻")
                return self._news_cache.copy()
            
            raise
    
    async def _fetch_impl(self) -> List[NewsItemModel]:
        """子类必须实现的获取数据方法"""
        raise NotImplementedError("子类必须实现_fetch_impl方法")

    async def _fetch_with_http_fallback(self) -> List[NewsItemModel]:
        """
        使用HTTP请求方式获取第一财经新闻和快讯数据
        作为Selenium方式的备选方案
        更新：适配最新的HTML结构
        """
        logger.info("开始使用HTTP请求获取第一财经数据")
        all_items = []
        
        headers = {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
            "Upgrade-Insecure-Requests": "1",
        }
        
        # 1. 获取快讯数据
        logger.info(f"获取快讯数据，URL: {self.BRIEF_URL}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.BRIEF_URL, headers=headers, timeout=30) as response:
                    logger.info(f"快讯页面状态码: {response.status}")
                    
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, "html.parser")
                        
                        # 首先定位id为onlist的元素，该元素包含了所有快讯
                        onlist_container = soup.select_one("#onlist")
                        if not onlist_container:
                            logger.warning("未找到#onlist容器，尝试其他选择器")
                            
                        # 根据新的HTML结构提取快讯项
                        brief_items = []
                        date_group = None
                        
                        if onlist_container:
                            # 找到所有的日期分组
                            date_headers = onlist_container.select("h3")
                            
                            # 找到所有快讯项 - 新结构中每个快讯是li.m-brief元素
                            brief_items = onlist_container.select("li.m-brief, li.m-brief.m-notimportant")
                            logger.info(f"从#onlist容器中找到 {len(brief_items)} 条快讯")
                            
                            if date_headers and not date_headers[0].get("date_processed"):
                                # 记录第一个日期作为默认日期
                                date_group = date_headers[0].text.strip()
                                # 标记已处理，防止重复处理
                                date_headers[0]["date_processed"] = "true"
                                logger.info(f"找到日期分组: {date_group}")
                        
                        # 如果没有找到快讯，尝试使用旧的选择器
                        if not brief_items:
                            brief_items = soup.select(".flash-item, .brief-item, .new-flash-list .item")
                            logger.info(f"使用备用选择器找到 {len(brief_items)} 条快讯")
                        
                        logger.info(f"总共找到 {len(brief_items)} 条快讯")
                        
                        # 处理每条快讯
                        for index, item in enumerate(brief_items):
                            try:
                                # 提取时间 - 新结构中时间在<span>标签里
                                time_elem = item.select_one("p > span:first-child")
                                time_text = time_elem.text.strip() if time_elem else ""
                                
                                # 提取内容 - 新结构中内容在第二个span标签里
                                content_elem = item.select_one("p > span:nth-child(2)")
                                
                                # 如果没有找到上述结构，尝试直接从p元素获取内容
                                if not content_elem:
                                    content_elem = item.select_one("p")
                                    # 如果有时间元素，需要去除时间部分
                                    if content_elem and time_text:
                                        content = content_elem.text.strip().replace(time_text, "", 1)
                                    else:
                                        content = content_elem.text.strip() if content_elem else ""
                                else:
                                    content = content_elem.text.strip()
                                
                                # 检查内容中是否有加粗文本
                                bold_elem = item.select_one("p span b")
                                title_text = bold_elem.text.strip() if bold_elem else ""
                                
                                # 如果找到了标题，从内容中去除标题部分
                                if title_text and content.startswith(title_text):
                                    # 去除标题，保留其他内容
                                    content = content[len(title_text):].strip()
                                    # 如果内容以分隔符开始，去除分隔符
                                    if content.startswith("|"):
                                        content = content[1:].strip()
                                
                                # 提取链接
                                url = ""
                                # 检查是否有股票信息区域
                                stock_div = item.select_one(".m-gp1, .m-stock")
                                if stock_div:
                                    # 从股票信息中提取链接
                                    stock_link = stock_div.select_one("a")
                                    if stock_link and stock_link.get("href"):
                                        url = stock_link.get("href")
                                
                                # 如果没有股票链接，尝试从整个item中获取链接
                                if not url:
                                    link_elem = item.find("a")
                                    if link_elem and link_elem.get("href"):
                                        url = link_elem.get("href")
                                
                                # 格式化URL
                                if url and not url.startswith("http"):
                                    if url.startswith("/"):
                                        url = f"https://www.yicai.com{url}"
                                    else:
                                        url = f"https://www.yicai.com/{url}"
                                
                                # 解析时间
                                published_at = datetime.datetime.now()
                                if time_text:
                                    try:
                                        # 处理新格式的时间 "HH:MM"
                                        if re.match(r'\d{2}:\d{2}', time_text):
                                            # 今日时间 时:分
                                            today = datetime.datetime.now().date()
                                            hour, minute = time_text.split(':')
                                            published_at = datetime.datetime.combine(
                                                today, datetime.time(int(hour), int(minute))
                                            )
                                            
                                            # 如果有日期分组，使用日期分组的日期
                                            if date_group:
                                                try:
                                                    # 尝试解析日期组（格式如"2025.03.31"）
                                                    date_match = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', date_group)
                                                    if date_match:
                                                        year, month, day = map(int, date_match.groups())
                                                        group_date = datetime.date(year, month, day)
                                                        published_at = datetime.datetime.combine(
                                                            group_date, 
                                                            datetime.time(int(hour), int(minute))
                                                        )
                                                except Exception as date_e:
                                                    logger.warning(f"解析日期分组失败: {date_group}, 错误: {str(date_e)}")
                                        # 处理其他格式的时间
                                        elif re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', time_text):
                                            # 完整的日期时间
                                            published_at = datetime.datetime.strptime(time_text, "%Y-%m-%d %H:%M")
                                        elif re.match(r'\d{2}-\d{2} \d{2}:\d{2}', time_text):
                                            # 月-日 时:分
                                            current_year = datetime.datetime.now().year
                                            date_part, time_part = time_text.split(' ')
                                            month, day = date_part.split('-')
                                            hour, minute = time_part.split(':')
                                            published_at = datetime.datetime(
                                                current_year, int(month), int(day), 
                                                int(hour), int(minute)
                                            )
                                    except Exception as e:
                                        logger.warning(f"解析时间失败: {time_text}, 错误: {str(e)}")
                                
                                # 检查内容是否为空
                                if not (title_text or content):
                                    logger.warning(f"跳过没有标题和内容的快讯项 {index}")
                                    continue
                                
                                # 生成最终内容
                                final_content = title_text
                                if content:
                                    if final_content:
                                        final_content += " | " + content
                                    else:
                                        final_content = content
                                
                                # 检查是否有"重要"标记
                                is_important = not item.has_attr('class') or 'm-notimportant' not in item['class']
                                
                                # 生成唯一ID
                                brief_id = hashlib.md5(f"yicai-brief-{final_content}-{time_text}".encode()).hexdigest()
                                
                                # 创建新闻项
                                news_item = self.create_news_item(
                                    id=brief_id,
                                    title=title_text or (content[:50] + "..." if len(content) > 50 else content),
                                    url=url,
                                    content=final_content,
                                    summary=final_content,
                                    published_at=published_at,
                                    extra={
                                        "time_text": time_text,
                                        "type": "brief",
                                        "rank": index + 1,
                                        "source_from": "http_fallback",
                                        "important": is_important
                                    }
                                )
                                
                                all_items.append(news_item)
                                
                            except Exception as e:
                                logger.error(f"处理快讯项 {index} 失败: {str(e)}")
        except Exception as e:
            logger.error(f"获取快讯数据失败: {str(e)}")
        
        # 2. 获取新闻数据
        logger.info(f"获取新闻数据，URL: {self.NEWS_URL}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.NEWS_URL, headers=headers, timeout=30) as response:
                    logger.info(f"新闻页面状态码: {response.status}")
                    
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, "html.parser")
                        
                        # 使用最新的HTML结构查找新闻项
                        news_container = soup.select_one("#newslist")
                        if news_container:
                            news_items = news_container.select("a.f-db")
                            logger.info(f"找到 {len(news_items)} 条新闻")
                            
                            for index, item in enumerate(news_items):
                                try:
                                    # 提取链接
                                    href = item.get("href", "")
                                    url = f"https://www.yicai.com{href}" if href.startswith("/") else href
                                    
                                    # 提取标题
                                    title_elem = item.select_one("h2")
                                    title = title_elem.text.strip() if title_elem else ""
                                    
                                    # 提取摘要
                                    summary_elem = item.select_one("p")
                                    summary = summary_elem.text.strip() if summary_elem else ""
                                    
                                    # 提取时间
                                    time_elem = item.select_one(".rightspan span:last-child")
                                    time_text = time_elem.text.strip() if time_elem else ""
                                    
                                    # 提取图片URL
                                    img_elem = item.select_one("img.u-img")
                                    image_url = img_elem.get("src", "") if img_elem else ""
                                    
                                    # 解析时间
                                    published_at = datetime.datetime.now()
                                    if time_text:
                                        try:
                                            # 处理时间格式
                                            if re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', time_text):
                                                published_at = datetime.datetime.strptime(time_text, "%Y-%m-%d %H:%M")
                                            elif re.match(r'\d{2}-\d{2} \d{2}:\d{2}', time_text):
                                                current_year = datetime.datetime.now().year
                                                date_part, time_part = time_text.split(' ')
                                                month, day = date_part.split('-')
                                                hour, minute = time_part.split(':')
                                                published_at = datetime.datetime(
                                                    current_year, int(month), int(day), 
                                                    int(hour), int(minute)
                                                )
                                        except:
                                            pass
                                    
                                    # 如果标题为空则跳过
                                    if not title:
                                        continue
                                    
                                    # 生成唯一ID
                                    news_id = hashlib.md5(f"yicai-news-{title}-{url}".encode()).hexdigest()
                                    
                                    # 创建新闻项
                                    news_item = self.create_news_item(
                                        id=news_id,
                                        title=title,
                                        url=url,
                                        summary=summary,
                                        image_url=image_url,
                                        published_at=published_at,
                                        extra={
                                            "time_text": time_text,
                                            "type": "news",
                                            "rank": index + 1,
                                            "source_from": "http_fallback"
                                        }
                                    )
                                    
                                    all_items.append(news_item)
                                    
                                except Exception as e:
                                    logger.error(f"处理新闻项 {index} 失败: {str(e)}")
                        else:
                            logger.warning("未找到新闻列表容器 #newslist")
                    else:
                        logger.error(f"获取新闻页面失败，状态码: {response.status}")
        except Exception as e:
            logger.error(f"获取新闻数据失败: {str(e)}")
        
        logger.info(f"HTTP回退模式总共获取到 {len(all_items)} 条数据")
        return all_items
    
    # 清理缓存
    async def clear_cache(self):
        """清理缓存数据"""
        async with self._cache_lock:
            self._news_cache = []
            self._last_cache_update = 0
        logger.info("已清理第一财经缓存")
    
    # 重写关闭方法，确保清理资源
    async def close(self):
        """关闭资源"""
        await self.clear_cache()
        
        # 关闭WebDriver
        if self._driver:
            try:
                await self._close_driver()
            except Exception as e:
                logger.error(f"关闭WebDriver时出错: {str(e)}")
        
        await super().close()
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        实现基类要求的parse_response方法
        
        由于YiCaiNewsSource类使用Selenium和自定义的fetch方法进行数据获取和解析，
        这个方法仅作为满足抽象基类要求而存在，实际不会被直接调用。
        实际的解析逻辑在_fetch_brief, _fetch_news和相关方法中。
        
        Args:
            response: HTML响应内容
            
        Returns:
            空列表，因为该方法不会被实际使用
        """
        logger.warning("YiCaiNewsSource.parse_response被直接调用，这不是预期的使用方式。"
                      "YiCai适配器使用专用的Selenium方法获取新闻。")
        return []

# 快讯适配器类
class YiCaiBriefSource(YiCaiBaseSource):
    """
    第一财经快讯适配器 - 专门用于获取第一财经快讯内容
    """
    
    def __init__(
        self,
        source_id: str = "yicai-brief",
        name: str = "第一财经快讯",
        url: str = "https://www.yicai.com/brief/",
        update_interval: int = 900,  # 15分钟，快讯更新较频繁
        cache_ttl: int = 600,  # 10分钟
        category: str = "finance",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        # 强制统一source_id
        if source_id != "yicai-brief":
            logger.warning(f"源ID '{source_id}' 被统一为标准ID 'yicai-brief'")
            source_id = "yicai-brief"
            
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
    
    async def _fetch_impl(self) -> List[NewsItemModel]:
        """实际获取快讯数据的内部方法"""
        # 重置HTTP备用标志
        self._tried_http_fallback = False
        
        try:
            # 获取快讯
            brief_items = await self._fetch_brief()
            
            # 如果获取失败且有HTTP备用方法
            if not brief_items and self.config.get("use_http_fallback", True):
                logger.info("尝试使用HTTP备用方法获取快讯数据")
                fallback_news = await self._fetch_with_http_fallback()
                if fallback_news:
                    # 过滤出快讯类型的项目
                    brief_items = [item for item in fallback_news if item.extra.get("type") == "brief"]
            
            # 按时间排序（如果有发布时间）
            brief_items.sort(
                key=lambda x: x.published_at if x.published_at else datetime.datetime.now(),
                reverse=True  # 最新的在前面
            )
            
            logger.info(f"成功获取 {len(brief_items)} 条第一财经快讯数据")
            return brief_items
        except Exception as e:
            logger.error(f"获取第一财经快讯数据失败: {str(e)}")
            raise

    async def _fetch_brief(self) -> List[NewsItemModel]:
        """
        获取第一财经快讯数据
        """
        logger.info("开始获取第一财经快讯数据")
        driver = await self._get_driver()
        if driver is None:
            logger.error("WebDriver创建失败")
            raise RuntimeError("无法获取第一财经快讯：WebDriver创建失败")
        
        brief_items = []
        try:
            # 访问快讯页面
            logger.info(f"访问快讯URL: {self.BRIEF_URL}")
            loop = asyncio.get_event_loop()
            
            try:
                # 设置超时
                page_load_timeout = self.config.get("selenium_timeout", 30)
                await loop.run_in_executor(
                    None, 
                    lambda: driver.set_page_load_timeout(page_load_timeout)
                )
                
                # 访问URL
                await loop.run_in_executor(None, lambda: driver.get(self.BRIEF_URL))
                
            except Exception as e:
                logger.warning(f"页面加载异常: {str(e)}")
                raise RuntimeError(f"无法获取第一财经快讯：页面加载失败")
            
            # 等待页面加载完成
            await asyncio.sleep(3)
            
            # 等待快讯容器元素加载 - 等待新的容器结构 #onlist
            try:
                await loop.run_in_executor(
                    None,
                    lambda: WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "#onlist, .brief-list, .m-brief-list"))
                    )
                )
            except Exception as wait_e:
                logger.warning(f"等待快讯容器加载超时: {str(wait_e)}")
            
            # 获取所有快讯项
            logger.info("提取快讯数据")
            try:
                # 首先尝试查找新结构中的快讯容器 #onlist
                onlist_container = None
                try:
                    onlist_container = await loop.run_in_executor(
                        None,
                        lambda: driver.find_element(By.CSS_SELECTOR, "#onlist")
                    )
                    logger.info("找到新结构快讯容器 #onlist")
                except Exception:
                    logger.info("未找到新结构快讯容器 #onlist，将尝试其他选择器")
                
                date_group = None
                brief_items_elements = []
                
                # 如果找到了新的容器，则获取日期和快讯项
                if onlist_container:
                    # 查找日期标题
                    date_headers = await loop.run_in_executor(
                        None,
                        lambda: onlist_container.find_elements(By.CSS_SELECTOR, "h3")
                    )
                    
                    if date_headers:
                        date_text = await loop.run_in_executor(
                            None,
                            lambda: date_headers[0].text.strip()
                        )
                        date_group = date_text
                        logger.info(f"找到日期分组: {date_group}")
                    
                    # 查找新结构中的快讯项
                    brief_items_elements = await loop.run_in_executor(
                        None,
                        lambda: onlist_container.find_elements(By.CSS_SELECTOR, "li.m-brief, li.m-brief.m-notimportant")
                    )
                    logger.info(f"在#onlist容器中找到 {len(brief_items_elements)} 个快讯项")
                
                # 如果没有在新结构中找到快讯项，尝试使用旧的选择器
                if not brief_items_elements:
                    logger.warning("未找到新结构快讯项，尝试其他选择器")
                    brief_items_elements = await loop.run_in_executor(
                        None,
                        lambda: driver.find_elements(By.CSS_SELECTOR, ".brief-item, .m-brief-item")
                    )
                    
                    if not brief_items_elements:
                        logger.warning("未找到快讯项元素，继续尝试其他选择器")
                        brief_items_elements = await loop.run_in_executor(
                            None,
                            lambda: driver.find_elements(By.CSS_SELECTOR, ".news-item, .brief-list>div")
                        )
                
                if brief_items_elements:
                    logger.info(f"总共找到 {len(brief_items_elements)} 个快讯项")
                    
                    for index, item in enumerate(brief_items_elements[:50]):  # 最多提取50条
                        try:
                            # 提取时间和内容 - 根据页面结构的不同尝试不同的选择器
                            
                            # 尝试新结构的时间选择器
                            time_text = ""
                            try:
                                # 新结构中时间是第一个span
                                time_element = await loop.run_in_executor(
                                    None,
                                    lambda: item.find_elements(By.CSS_SELECTOR, "p > span:first-child")
                                )
                                if time_element:
                                    time_text = await loop.run_in_executor(
                                        None,
                                        lambda: time_element[0].text.strip()
                                    )
                            except Exception:
                                logger.debug("使用新选择器提取时间失败，尝试旧选择器")
                            
                            # 如果新选择器失败，尝试旧选择器
                            if not time_text:
                                time_element = await loop.run_in_executor(
                                    None,
                                    lambda: item.find_elements(By.CSS_SELECTOR, ".time, .m-time, .brief-time")
                                )
                                if time_element:
                                    time_text = await loop.run_in_executor(
                                        None,
                                        lambda: time_element[0].text.strip()
                                    )
                            
                            # 提取标题和内容
                            title_text = ""
                            content_text = ""
                            
                            # 尝试提取加粗的标题
                            try:
                                bold_element = await loop.run_in_executor(
                                    None,
                                    lambda: item.find_elements(By.CSS_SELECTOR, "p span b")
                                )
                                if bold_element:
                                    title_text = await loop.run_in_executor(
                                        None,
                                        lambda: bold_element[0].text.strip()
                                    )
                            except Exception:
                                logger.debug("提取加粗标题失败")
                            
                            # 尝试提取内容 - 新结构
                            try:
                                # 获取整个p元素的文本
                                p_element = await loop.run_in_executor(
                                    None,
                                    lambda: item.find_elements(By.CSS_SELECTOR, "p")
                                )
                                if p_element:
                                    full_text = await loop.run_in_executor(
                                        None,
                                        lambda: p_element[0].text.strip()
                                    )
                                    
                                    # 如果有时间和标题，从全文中去除
                                    if time_text and title_text:
                                        content_part = full_text.replace(time_text, "", 1)
                                        if title_text in content_part:
                                            content_part = content_part.replace(title_text, "", 1)
                                        # 如果内容以分隔符开始，去除分隔符
                                        if content_part.strip().startswith("|"):
                                            content_part = content_part.strip()[1:].strip()
                                        content_text = content_part
                                    elif time_text:
                                        # 只有时间，没有标题
                                        content_text = full_text.replace(time_text, "", 1).strip()
                                    else:
                                        # 没有时间也没有标题
                                        content_text = full_text
                            except Exception as e:
                                logger.debug(f"提取内容失败: {str(e)}")
                            
                            # 如果新结构提取失败，尝试旧结构
                            if not content_text:
                                content_element = await loop.run_in_executor(
                                    None,
                                    lambda: item.find_elements(By.CSS_SELECTOR, ".content, .m-content, .brief-content")
                                )
                                
                                if content_element:
                                    content_text = await loop.run_in_executor(
                                        None,
                                        lambda: content_element[0].text.strip()
                                    )
                            
                            # 提取链接
                            url = ""
                            
                            # 检查是否有股票信息区域，可能包含链接
                            try:
                                stock_div = await loop.run_in_executor(
                                    None,
                                    lambda: item.find_elements(By.CSS_SELECTOR, ".m-gp1, .m-stock")
                                )
                                if stock_div:
                                    stock_link = await loop.run_in_executor(
                                        None,
                                        lambda: stock_div[0].find_elements(By.TAG_NAME, "a")
                                    )
                                    if stock_link:
                                        url = await loop.run_in_executor(
                                            None,
                                            lambda: stock_link[0].get_attribute("href")
                                        )
                            except Exception:
                                logger.debug("提取股票链接失败")
                            
                            # 如果没有从股票区域获取到链接，尝试从整个元素获取
                            if not url:
                                try:
                                    url_element = await loop.run_in_executor(
                                        None,
                                        lambda: item.find_element(By.TAG_NAME, "a")
                                    )
                                    
                                    url = await loop.run_in_executor(
                                        None,
                                        lambda: url_element.get_attribute("href")
                                    )
                                except:
                                    # 如果没有链接，使用当前页面URL
                                    url = self.BRIEF_URL
                            
                            # 解析时间
                            published_at = datetime.datetime.now()
                            try:
                                # 处理时间格式，格式可能是 "14:49" 或 "MM-DD HH:MM"
                                if re.match(r'\d{2}:\d{2}', time_text):
                                    # 只有时分，使用当前日期
                                    today = datetime.datetime.now().date()
                                    time_parts = time_text.split(':')
                                    published_at = datetime.datetime.combine(
                                        today,
                                        datetime.time(int(time_parts[0]), int(time_parts[1]))
                                    )
                                    
                                    # 如果有日期分组，使用日期分组的日期
                                    if date_group:
                                        try:
                                            # 尝试解析日期组（格式如"2025.03.31"）
                                            date_match = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', date_group)
                                            if date_match:
                                                year, month, day = map(int, date_match.groups())
                                                group_date = datetime.date(year, month, day)
                                                published_at = datetime.datetime.combine(
                                                    group_date, 
                                                    datetime.time(int(time_parts[0]), int(time_parts[1]))
                                                )
                                        except Exception as date_e:
                                            logger.warning(f"解析日期分组失败: {date_group}, 错误: {str(date_e)}")
                                elif re.match(r'\d{2}-\d{2} \d{2}:\d{2}', time_text):
                                    # 月-日 时:分
                                    current_year = datetime.datetime.now().year
                                    date_part, time_part = time_text.split(' ')
                                    month, day = date_part.split('-')
                                    hour, minute = time_part.split(':')
                                    published_at = datetime.datetime(
                                        current_year, int(month), int(day), 
                                        int(hour), int(minute)
                                    )
                            except Exception as time_e:
                                logger.warning(f"解析时间失败: {str(time_e)}")
                            
                            # 检查是否有内容
                            if not (title_text or content_text):
                                logger.warning(f"跳过没有标题和内容的快讯项 {index}")
                                continue
                            
                            # 生成最终内容
                            final_content = title_text
                            if content_text:
                                if final_content:
                                    final_content += " | " + content_text
                                else:
                                    final_content = content_text
                            
                            # 检查是否为重要快讯
                            is_important = False
                            try:
                                item_class = await loop.run_in_executor(
                                    None,
                                    lambda: item.get_attribute("class")
                                )
                                # 如果没有m-notimportant类，则为重要快讯
                                is_important = "m-notimportant" not in (item_class or "")
                            except Exception:
                                logger.debug("检查快讯重要性失败")
                            
                            # 生成唯一ID
                            brief_id = hashlib.md5(f"yicai-brief-{final_content}-{time_text}".encode()).hexdigest()
                            
                            # 创建新闻项
                            brief_item = self.create_news_item(
                                id=brief_id,
                                title=title_text or (content_text[:100] if content_text else "第一财经快讯"),
                                url=url,
                                content=final_content,
                                summary=final_content,
                                published_at=published_at,
                                extra={
                                    "time_text": time_text,
                                    "type": "brief",
                                    "rank": index + 1,
                                    "source_from": "selenium",
                                    "important": is_important
                                }
                            )
                            
                            brief_items.append(brief_item)
                            
                        except Exception as item_e:
                            logger.error(f"处理快讯项 {index} 失败: {str(item_e)}")
                else:
                    logger.warning("未找到任何快讯项，尝试从页面源代码提取数据")
                    
                    # 尝试从页面源代码提取数据
                    page_source = await loop.run_in_executor(None, lambda: driver.page_source)
                    
                    soup = BeautifulSoup(page_source, 'html.parser')
                    
                    # 首先尝试找到#onlist容器
                    onlist_container = soup.select_one("#onlist")
                    if onlist_container:
                        logger.info("从页面源代码中找到#onlist容器")
                        
                        # 获取日期
                        date_headers = onlist_container.select("h3")
                        date_group = date_headers[0].text.strip() if date_headers else None
                        
                        # 获取所有快讯项
                        brief_items_bs = onlist_container.select("li.m-brief, li.m-brief.m-notimportant")
                        logger.info(f"从#onlist容器中找到 {len(brief_items_bs)} 条快讯")
                        
                        # 处理每条快讯
                        for index, item in enumerate(brief_items_bs[:50]):  # 最多处理50条
                            try:
                                # 提取时间
                                time_element = item.select_one("p > span:first-child")
                                time_text = time_element.text.strip() if time_element else ""
                                
                                # 提取标题和内容
                                title_element = item.select_one("p span b")
                                title_text = title_element.text.strip() if title_element else ""
                                
                                # 提取完整内容
                                p_element = item.select_one("p")
                                full_text = p_element.text.strip() if p_element else ""
                                
                                # 处理内容
                                content_text = ""
                                if full_text:
                                    # 如果有时间和标题，从全文中去除
                                    if time_text and title_text:
                                        content_part = full_text.replace(time_text, "", 1)
                                        if title_text in content_part:
                                            content_part = content_part.replace(title_text, "", 1)
                                        # 如果内容以分隔符开始，去除分隔符
                                        if content_part.strip().startswith("|"):
                                            content_part = content_part.strip()[1:].strip()
                                        content_text = content_part
                                    elif time_text:
                                        # 只有时间，没有标题
                                        content_text = full_text.replace(time_text, "", 1).strip()
                                    else:
                                        # 没有时间也没有标题
                                        content_text = full_text
                                
                                # 提取链接
                                url = ""
                                stock_div = item.select_one(".m-gp1, .m-stock")
                                if stock_div:
                                    stock_link = stock_div.select_one("a")
                                    if stock_link and stock_link.get("href"):
                                        url = stock_link.get("href")
                                
                                if not url:
                                    link_elem = item.find("a")
                                    if link_elem and link_elem.get("href"):
                                        url = link_elem.get("href")
                                
                                # 如果链接不是完整URL，添加域名
                                if url and not url.startswith("http"):
                                    url = f"https://www.yicai.com{url}" if url.startswith("/") else f"https://www.yicai.com/{url}"
                                
                                # 解析时间
                                published_at = datetime.datetime.now()
                                if time_text:
                                    try:
                                        # 处理时间格式
                                        if re.match(r'\d{2}:\d{2}', time_text):
                                            # 今天的时间
                                            today = datetime.datetime.now().date()
                                            hour, minute = time_text.split(':')
                                            published_at = datetime.datetime.combine(
                                                today, 
                                                datetime.time(int(hour), int(minute))
                                            )
                                            
                                            # 如果有日期标题，使用日期标题的日期
                                            if date_group:
                                                date_match = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', date_group)
                                                if date_match:
                                                    year, month, day = map(int, date_match.groups())
                                                    group_date = datetime.date(year, month, day)
                                                    published_at = datetime.datetime.combine(
                                                        group_date, 
                                                        datetime.time(int(hour), int(minute))
                                                    )
                                    except Exception as bs_date_e:
                                        logger.warning(f"解析BeautifulSoup时间失败: {str(bs_date_e)}")
                                
                                # 生成最终内容
                                final_content = title_text
                                if content_text:
                                    if final_content:
                                        final_content += " | " + content_text
                                    else:
                                        final_content = content_text
                                
                                # 检查是否为重要快讯
                                is_important = 'm-notimportant' not in (item.get('class') or [])
                                
                                # 生成唯一ID
                                brief_id = hashlib.md5(f"yicai-brief-{final_content}-{time_text}".encode()).hexdigest()
                                
                                # 创建新闻项
                                brief_item = self.create_news_item(
                                    id=brief_id,
                                    title=title_text or (content_text[:100] if content_text else "第一财经快讯"),
                                    url=url or self.BRIEF_URL,
                                    content=final_content,
                                    summary=final_content,
                                    published_at=published_at,
                                    extra={
                                        "time_text": time_text,
                                        "type": "brief",
                                        "rank": index + 1,
                                        "source_from": "beautifulsoup",
                                        "important": is_important
                                    }
                                )
                                
                                brief_items.append(brief_item)
                                
                            except Exception as bs_e:
                                logger.error(f"使用BeautifulSoup处理快讯项 {index} 失败: {str(bs_e)}")
                    else:
                        # 尝试使用旧的选择器
                        brief_containers = soup.select(".brief-list, .m-brief-list, .news-list")
                        if brief_containers:
                            logger.info("从页面源代码中找到旧版快讯容器")
                            # 使用旧版处理逻辑
                            for container in brief_containers:
                                brief_items_elements = container.select(".brief-item, .m-brief-item, .news-item")
                                
                                for index, item in enumerate(brief_items_elements[:50]):
                                    try:
                                        # 提取时间
                                        time_element = item.select_one(".time, .m-time, .brief-time")
                                        time_text = time_element.text.strip() if time_element else ""
                                        
                                        # 提取内容
                                        content_element = item.select_one(".content, .m-content, .brief-content")
                                        content_text = content_element.text.strip() if content_element else ""
                                        
                                        # 提取链接
                                        url_element = item.select_one("a")
                                        url = url_element.get("href") if url_element else self.BRIEF_URL
                                        
                                        # 解析时间
                                        published_at = datetime.datetime.now()
                                        if time_text:
                                            try:
                                                # 处理时间格式
                                                if re.match(r'\d{2}:\d{2}', time_text):
                                                    # 今天的时间
                                                    today = datetime.datetime.now().date()
                                                    hour, minute = time_text.split(':')
                                                    published_at = datetime.datetime.combine(
                                                        today, 
                                                        datetime.time(int(hour), int(minute))
                                                    )
                                            except Exception as time_e:
                                                logger.warning(f"解析时间失败: {str(time_e)}")
                                        
                                        # 生成唯一ID
                                        brief_id = hashlib.md5(f"yicai-brief-{content_text}-{time_text}".encode()).hexdigest()
                                        
                                        # 创建新闻项
                                        brief_item = self.create_news_item(
                                            id=brief_id,
                                            title=content_text[:100],  # 使用内容前100字作为标题
                                            url=url,
                                            content=content_text,
                                            summary=content_text,
                                            published_at=published_at,
                                            extra={
                                                "time_text": time_text,
                                                "type": "brief",
                                                "rank": index + 1,
                                                "source_from": "beautifulsoup_old"
                                            }
                                        )
                                        
                                        brief_items.append(brief_item)
                                    except Exception as item_e:
                                        logger.error(f"处理旧版快讯项 {index} 失败: {str(item_e)}")
            except Exception as extract_e:
                logger.error(f"提取快讯失败: {str(extract_e)}")
                raise RuntimeError(f"提取快讯失败: {str(extract_e)}")
                
        except Exception as e:
            logger.error(f"获取第一财经快讯失败: {str(e)}")
            raise
        finally:
            # 关闭WebDriver
            try:
                await self._close_driver()
            except Exception as close_e:
                logger.error(f"关闭WebDriver失败: {str(close_e)}")
        
        logger.info(f"成功获取 {len(brief_items)} 条第一财经快讯")
        return brief_items

# 新闻适配器类
class YiCaiNewsSource(YiCaiBaseSource):
    """
    第一财经新闻适配器 - 专门用于获取第一财经新闻内容
    """
    
    def __init__(
        self,
        source_id: str = "yicai-news",
        name: str = "第一财经新闻",
        url: str = "https://www.yicai.com/news/",
        update_interval: int = 1800,  # 30分钟，新闻更新较慢
        cache_ttl: int = 1200,  # 20分钟
        category: str = "finance",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        # 强制统一source_id
        if source_id != "yicai-news":
            logger.warning(f"源ID '{source_id}' 被统一为标准ID 'yicai-news'")
            source_id = "yicai-news"
            
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
    
    async def _fetch_impl(self) -> List[NewsItemModel]:
        """实际获取新闻数据的内部方法"""
        # 重置HTTP备用标志
        self._tried_http_fallback = False
        
        try:
            # 获取新闻
            news_items = await self._fetch_news()
            
            # 如果获取失败且有HTTP备用方法
            if not news_items and self.config.get("use_http_fallback", True):
                logger.info("尝试使用HTTP备用方法获取新闻数据")
                fallback_news = await self._fetch_with_http_fallback()
                if fallback_news:
                    # 过滤出新闻类型的项目
                    news_items = [item for item in fallback_news if item.extra.get("type") == "news"]
            
            # 按时间排序（如果有发布时间）
            news_items.sort(
                key=lambda x: x.published_at if x.published_at else datetime.datetime.now(),
                reverse=True  # 最新的在前面
            )
            
            logger.info(f"成功获取 {len(news_items)} 条第一财经新闻数据")
            return news_items
        except Exception as e:
            logger.error(f"获取第一财经新闻数据失败: {str(e)}")
            raise
            
    async def _fetch_news(self) -> List[NewsItemModel]:
        """
        获取第一财经新闻数据
        针对最新的DOM结构进行优化，更准确地获取新闻列表
        """
        logger.info("开始获取第一财经新闻数据")
        driver = await self._get_driver()
        if driver is None:
            logger.error("WebDriver创建失败")
            raise RuntimeError("无法获取第一财经新闻：WebDriver创建失败")
        
        news_items = []
        try:
            # 访问新闻页面
            logger.info(f"访问新闻URL: {self.NEWS_URL}")
            loop = asyncio.get_event_loop()
            
            try:
                # 设置超时
                page_load_timeout = self.config.get("selenium_timeout", 30)
                await loop.run_in_executor(
                    None, 
                    lambda: driver.set_page_load_timeout(page_load_timeout)
                )
                
                # 访问URL
                await loop.run_in_executor(None, lambda: driver.get(self.NEWS_URL))
                
            except Exception as e:
                logger.warning(f"页面加载异常: {str(e)}")
                raise RuntimeError(f"无法获取第一财经新闻：页面加载失败")
            
            # 等待页面加载完成
            await asyncio.sleep(3)
            
            # 等待新闻列表元素加载 - 使用最新的DOM selector
            try:
                await loop.run_in_executor(
                    None,
                    lambda: WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "#newslist"))
                    )
                )
            except Exception as wait_e:
                logger.warning(f"等待新闻列表加载超时: {str(wait_e)}")
            
            # 获取所有新闻项
            logger.info("提取新闻数据")
            try:
                # 查找新闻项元素 - 使用最新的DOM结构
                news_items_elements = await loop.run_in_executor(
                    None,
                    lambda: driver.find_elements(By.CSS_SELECTOR, "#newslist a.f-db")
                )
                
                if not news_items_elements:
                    logger.warning("未找到新闻项元素，尝试其他选择器")
                    # 尝试其他可能的选择器
                    news_items_elements = await loop.run_in_executor(
                        None,
                        lambda: driver.find_elements(By.CSS_SELECTOR, ".m-list, .news-list, .news-items")
                    )
                
                if news_items_elements:
                    logger.info(f"找到 {len(news_items_elements)} 个新闻项")
                    
                    for index, item in enumerate(news_items_elements[:50]):  # 最多提取50条
                        try:
                            # 提取标题 - 优化选择器
                            title_element = await loop.run_in_executor(
                                None,
                                lambda: item.find_elements(By.CSS_SELECTOR, "h2")
                            )
                            
                            title = ""
                            if title_element:
                                title = await loop.run_in_executor(
                                    None,
                                    lambda: title_element[0].text.strip()
                                )
                            
                            # 提取链接
                            url = ""
                            try:
                                url = await loop.run_in_executor(
                                    None,
                                    lambda: item.get_attribute("href")
                                )
                            except:
                                # 如果没有链接，使用当前页面URL
                                url = self.NEWS_URL
                            
                            # 提取摘要 - 优化选择器
                            summary_element = await loop.run_in_executor(
                                None,
                                lambda: item.find_elements(By.CSS_SELECTOR, "p")
                            )
                            
                            summary = ""
                            if summary_element:
                                summary = await loop.run_in_executor(
                                    None,
                                    lambda: summary_element[0].text.strip()
                                )
                            
                            # 提取时间 - 优化选择器
                            time_element = await loop.run_in_executor(
                                None,
                                lambda: item.find_elements(By.CSS_SELECTOR, ".rightspan span:last-child")
                            )
                            
                            time_text = ""
                            if time_element:
                                time_text = await loop.run_in_executor(
                                    None,
                                    lambda: time_element[0].text.strip()
                                )
                            
                            # 提取图片URL - 优化选择器
                            image_url = ""
                            try:
                                img_element = await loop.run_in_executor(
                                    None,
                                    lambda: item.find_element(By.CSS_SELECTOR, "img.u-img")
                                )
                                
                                if img_element:
                                    image_url = await loop.run_in_executor(
                                        None,
                                        lambda: img_element.get_attribute("src")
                                    )
                            except:
                                pass
                            
                            # 解析时间
                            published_at = None
                            if time_text:
                                try:
                                    # 处理"5分钟前"，"1小时前"等格式
                                    if "分钟前" in time_text:
                                        minutes = int(time_text.replace("分钟前", "").strip())
                                        published_at = datetime.datetime.now() - datetime.timedelta(minutes=minutes)
                                    elif "小时前" in time_text:
                                        hours = int(time_text.replace("小时前", "").strip())
                                        published_at = datetime.datetime.now() - datetime.timedelta(hours=hours)
                                    elif "天前" in time_text:
                                        days = int(time_text.replace("天前", "").strip())
                                        published_at = datetime.datetime.now() - datetime.timedelta(days=days)
                                    else:
                                        # 使用当前时间
                                        published_at = datetime.datetime.now()
                                except Exception as time_e:
                                    logger.warning(f"解析时间失败: {str(time_e)}")
                                    published_at = datetime.datetime.now()
                            else:
                                published_at = datetime.datetime.now()
                            
                            # 如果没有标题则跳过
                            if not title:
                                continue
                            
                            # 构建完整URL
                            if url and not url.startswith("http"):
                                if url.startswith("/"):
                                    url = f"https://www.yicai.com{url}"
                                else:
                                    url = f"https://www.yicai.com/{url}"
                            
                            # 生成唯一ID
                            news_id = hashlib.md5(f"yicai-news-{title}-{url}".encode()).hexdigest()
                            
                            # 创建新闻项
                            news_item = self.create_news_item(
                                id=news_id,
                                title=title,
                                url=url,
                                summary=summary,
                                image_url=image_url,
                                published_at=published_at,
                                extra={
                                    "time_text": time_text,
                                    "type": "news",
                                    "rank": index + 1,
                                    "source_from": "selenium"
                                }
                            )
                            
                            news_items.append(news_item)
                            
                        except Exception as item_e:
                            logger.error(f"处理新闻项 {index} 失败: {str(item_e)}")
                else:
                    logger.warning("未找到任何新闻项")
                    
                    # 尝试从页面源代码提取数据
                    logger.info("尝试从页面源代码提取数据")
                    page_source = await loop.run_in_executor(None, lambda: driver.page_source)
                    
                    soup = BeautifulSoup(page_source, 'html.parser')
                    
                    # 使用优化的选择器
                    news_container = soup.select_one("#newslist")
                    
                    if news_container:
                        news_items_elements = news_container.select("a.f-db")
                        
                        for index, item in enumerate(news_items_elements[:50]):
                            try:
                                # 提取标题
                                title_element = item.select_one("h2")
                                title = title_element.text.strip() if title_element else ""
                                
                                # 提取链接
                                href = item.get("href", "")
                                url = f"https://www.yicai.com{href}" if href.startswith("/") else href
                                
                                # 提取摘要
                                summary_element = item.select_one("p")
                                summary = summary_element.text.strip() if summary_element else ""
                                
                                # 提取时间
                                time_element = item.select_one(".rightspan span:last-child")
                                time_text = time_element.text.strip() if time_element else ""
                                
                                # 提取图片URL
                                img_element = item.select_one("img.u-img")
                                image_url = img_element.get("src") if img_element else ""
                                
                                # 解析时间
                                published_at = datetime.datetime.now()
                                if time_text:
                                    try:
                                        # 处理"5分钟前"，"1小时前"等格式
                                        if "分钟前" in time_text:
                                            minutes = int(time_text.replace("分钟前", "").strip())
                                            published_at = datetime.datetime.now() - datetime.timedelta(minutes=minutes)
                                        elif "小时前" in time_text:
                                            hours = int(time_text.replace("小时前", "").strip())
                                            published_at = datetime.datetime.now() - datetime.timedelta(hours=hours)
                                        elif "天前" in time_text:
                                            days = int(time_text.replace("天前", "").strip())
                                            published_at = datetime.datetime.now() - datetime.timedelta(days=days)
                                    except:
                                        pass
                                
                                # 如果标题为空则跳过
                                if not title:
                                    continue
                                
                                # 生成唯一ID
                                news_id = hashlib.md5(f"yicai-news-{title}-{url}".encode()).hexdigest()
                                
                                # 创建新闻项
                                news_item = self.create_news_item(
                                    id=news_id,
                                    title=title,
                                    url=url,
                                    summary=summary,
                                    image_url=image_url,
                                    published_at=published_at,
                                    extra={
                                        "time_text": time_text,
                                        "type": "news",
                                        "rank": index + 1,
                                        "source_from": "beautifulsoup"
                                    }
                                )
                                
                                news_items.append(news_item)
                                
                            except Exception as bs_e:
                                logger.error(f"使用BeautifulSoup处理新闻项 {index} 失败: {str(bs_e)}")
                    
            except Exception as extract_e:
                logger.error(f"提取新闻失败: {str(extract_e)}")
                raise RuntimeError(f"提取新闻失败: {str(extract_e)}")
                
        except Exception as e:
            logger.error(f"获取第一财经新闻失败: {str(e)}")
            raise
        finally:
            # 关闭WebDriver
            try:
                await self._close_driver()
            except Exception as close_e:
                logger.error(f"关闭WebDriver失败: {str(close_e)}")
        
        logger.info(f"成功获取 {len(news_items)} 条第一财经新闻")
        return news_items