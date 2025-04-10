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
from datetime import timedelta

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

    def _find_chromedriver_path(self):
        """
        查找ChromeDriver路径
        """
        # 定义可能的ChromeDriver路径
        system = platform.system()
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
                break
        
        if not chromedriver_path:
            # 如果没有找到，尝试直接使用默认的 'chromedriver'
            chromedriver_path = "chromedriver"
        
        return chromedriver_path

# 快讯适配器类
class YiCaiBriefSource(YiCaiBaseSource):
    """第一财经快讯数据源"""
    
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
        config = config or {}
        # 设置快讯专用配置
        config.update({
            "list_url": "https://www.yicai.com/brief/",
            "max_items": 30  # 快讯通常获取更多条目
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
    
    async def _fetch_impl(self) -> List[NewsItemModel]:
        """实现快讯获取方法"""
        logger.info("尝试获取第一财经快讯")
        try:
            return await self._fetch_brief()
        except Exception as e:
            logger.warning(f"获取第一财经快讯失败: {str(e)}")
            # 尝试使用HTTP备用方法
            return await self._fetch_brief_http()
    
    async def _fetch_brief(self) -> List[NewsItemModel]:
        """获取第一财经快讯"""
        logger.info("开始从第一财经获取快讯")
        
        driver = None
        try:
            # 判断是否已有WebDriver实例
            if not self.driver:
                logger.info("创建新的WebDriver实例")
                self.driver = self._create_driver()
            
            # 检查WebDriver实例是否创建成功
            if not self.driver:
                logger.warning("WebDriver创建失败，尝试使用HTTP方式获取快讯")
                return await self._fetch_brief_http()
            
            driver = self.driver
            
            # 记录当前系统和ChromeDriver信息（用于调试）
            logger.info(f"当前系统平台: {platform.system()}")
            logger.info(f"使用的ChromeDriver: {driver.capabilities.get('chrome', {}).get('chromedriverVersion', '未知')}")
            
            # 新闻列表URL
            url = self.config.get("list_url", "https://www.yicai.com/brief/")
            logger.info(f"访问第一财经快讯列表页: {url}")
            
            # 使用异步超时控制防止页面加载过长时间
            try:
                # 使用asyncio.wait_for来设置异步超时
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, lambda: driver.get(url)
                    ),
                    timeout=self.config.get("selenium_timeout", 30)
                )
            except asyncio.TimeoutError:
                logger.warning("访问第一财经快讯页面超时，尝试使用HTTP方式获取")
                return await self._fetch_brief_http()
            except Exception as e:
                logger.warning(f"访问第一财经快讯页面异常: {str(e)}")
                return await self._fetch_brief_http()
            
            # 等待新闻列表元素加载
            try:
                # 使用显式等待等待新闻列表元素
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".b-list"))
                )
                logger.info("快讯列表元素加载完成")
            except Exception as e:
                logger.warning(f"等待快讯列表元素超时: {str(e)}")
                # 尝试检查页面状态
                try:
                    page_source = driver.page_source
                    if len(page_source) < 1000:
                        logger.warning(f"页面内容异常短，可能未正确加载，内容长度: {len(page_source)}")
                    elif "forbidden" in page_source.lower() or "请求被拒绝" in page_source:
                        logger.warning("访问被拒绝，可能触发了网站防爬虫机制")
                    elif "404" in page_source or "找不到页面" in page_source:
                        logger.warning("页面返回404错误")
                except Exception:
                    pass
                
                return await self._fetch_brief_http()
            
            # 获取快讯列表
            news_items = []
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, ".b-list li")
                logger.info(f"找到 {len(elements)} 个快讯项")
                
                if not elements:
                    logger.warning("未找到任何快讯项，尝试使用HTTP方式获取")
                    return await self._fetch_brief_http()
                
                for element in elements[:self.config.get("max_items", 30)]:
                    try:
                        # 提取快讯信息
                        title_element = element.find_element(By.CSS_SELECTOR, ".f-title")
                        title = title_element.text.strip()
                        
                        # 提取链接
                        url = ""
                        try:
                            url_element = element.find_element(By.CSS_SELECTOR, "a")
                            url = url_element.get_attribute("href")
                        except Exception:
                            # 如果没有链接，使用当前页面URL加上锚点
                            url = f"{self.config.get('list_url')}#{hashlib.md5(title.encode()).hexdigest()[:8]}"
                        
                        if not title:
                            logger.debug("跳过标题为空的快讯项")
                            continue
                        
                        # 提取摘要（对于快讯，摘要通常就是标题）
                        summary = title
                        
                        # 提取发布时间（如果有）
                        published_at = datetime.now()
                        try:
                            time_element = element.find_element(By.CSS_SELECTOR, ".time")
                            time_text = time_element.text.strip()
                            
                            # 解析时间字符串
                            if "今天" in time_text:
                                # 今天的快讯，使用当前日期
                                today = datetime.now().date()
                                time_part = time_text.replace("今天", "").strip()
                                if ":" in time_part:
                                    hour, minute = map(int, time_part.split(":"))
                                    published_at = datetime.combine(today, time(hour, minute))
                            elif "分钟前" in time_text:
                                # 几分钟前的快讯
                                try:
                                    minutes = int(time_text.replace("分钟前", "").strip())
                                    published_at = datetime.now() - timedelta(minutes=minutes)
                                except ValueError:
                                    pass
                            elif "小时前" in time_text:
                                # 几小时前的快讯
                                try:
                                    hours = int(time_text.replace("小时前", "").strip())
                                    published_at = datetime.now() - timedelta(hours=hours)
                                except ValueError:
                                    pass
                            elif ":" in time_text:
                                # 只有时间的格式 (如 "14:30")
                                today = datetime.now().date()
                                hour, minute = map(int, time_text.split(":"))
                                published_at = datetime.combine(today, time(hour, minute))
                        except Exception as e:
                            logger.debug(f"解析发布时间失败: {str(e)}")
                        
                        # 创建快讯项
                        # 生成唯一ID
                        news_id = hashlib.md5(f"yicai-brief-{title}-{url}".encode()).hexdigest()
                        
                        news_item = self.create_news_item(
                            id=news_id,
                            title=title,
                            url=url,
                            summary=summary,
                            image_url="",  # 快讯通常没有图片
                            published_at=published_at,
                            extra={
                                "type": "brief",
                                "source_from": "selenium"
                            }
                        )
                        news_items.append(news_item)
                        
                    except Exception as item_e:
                        logger.warning(f"处理单个快讯项时出错: {str(item_e)}")
                        continue
                
                logger.info(f"成功解析 {len(news_items)} 个快讯项")
                
                if not news_items:
                    logger.warning("未能成功解析任何快讯项，尝试使用HTTP方式获取")
                    return await self._fetch_brief_http()
                
                return news_items
                
            except Exception as e:
                logger.warning(f"解析快讯列表时出错: {str(e)}")
                return await self._fetch_brief_http()
            
        except Exception as e:
            logger.warning(f"使用Selenium获取第一财经快讯失败: {str(e)}")
            # 尝试使用HTTP方式获取
            return await self._fetch_brief_http()
            
        finally:
            # 不关闭driver，留给后续使用
            pass
    
    async def _fetch_brief_http(self) -> List[NewsItemModel]:
        """使用HTTP方式获取快讯（备用方法）"""
        logger.info("尝试使用HTTP方式获取第一财经快讯")
        
        try:
            url = self.config.get("list_url", "https://www.yicai.com/brief/")
            
            # 使用aiohttp进行异步HTTP请求
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {
                    "User-Agent": random.choice(self.USER_AGENTS),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
                }
                
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.warning(f"HTTP请求返回状态码 {response.status}")
                        return []
                    
                    html = await response.text()
                    
                    # 使用BeautifulSoup解析HTML
                    soup = BeautifulSoup(html, "html.parser")
                    
                    # 查找快讯列表
                    brief_list = soup.select(".b-list li")
                    logger.info(f"HTTP方式找到 {len(brief_list)} 个快讯项")
                    
                    if not brief_list:
                        logger.warning("HTTP方式未找到任何快讯项")
                        return []
                    
                    news_items = []
                    for item in brief_list[:self.config.get("max_items", 30)]:
                        try:
                            # 提取标题
                            title_element = item.select_one(".f-title")
                            if not title_element:
                                continue
                                
                            title = title_element.get_text(strip=True)
                            
                            # 提取链接
                            url_element = item.select_one("a")
                            url = url_element.get("href", "") if url_element else ""
                            
                            if not url:
                                # 如果没有链接，使用当前页面URL加上锚点
                                url = f"{self.config.get('list_url')}#{hashlib.md5(title.encode()).hexdigest()[:8]}"
                            elif not url.startswith("http"):
                                # 修正相对URL
                                url = f"https://www.yicai.com{url}"
                            
                            # 对于快讯，摘要通常就是标题
                            summary = title
                            
                            # 提取发布时间
                            published_at = datetime.now()
                            time_element = item.select_one(".time")
                            if time_element:
                                time_text = time_element.get_text(strip=True)
                                # 应用与上面相同的时间解析逻辑
                                if "今天" in time_text:
                                    today = datetime.now().date()
                                    time_part = time_text.replace("今天", "").strip()
                                    if ":" in time_part:
                                        hour, minute = map(int, time_part.split(":"))
                                        published_at = datetime.combine(today, time(hour, minute))
                                elif "分钟前" in time_text:
                                    try:
                                        minutes = int(time_text.replace("分钟前", "").strip())
                                        published_at = datetime.now() - timedelta(minutes=minutes)
                                    except ValueError:
                                        pass
                                elif "小时前" in time_text:
                                    try:
                                        hours = int(time_text.replace("小时前", "").strip())
                                        published_at = datetime.now() - timedelta(hours=hours)
                                    except ValueError:
                                        pass
                            
                            # 生成唯一ID
                            news_id = hashlib.md5(f"yicai-brief-{title}-{url}".encode()).hexdigest()
                            
                            # 创建快讯项
                            news_item = self.create_news_item(
                                id=news_id,
                                title=title,
                                url=url,
                                summary=summary,
                                image_url="",  # 快讯通常没有图片
                                published_at=published_at,
                                extra={
                                    "type": "brief",
                                    "source_from": "http"
                                }
                            )
                            news_items.append(news_item)
                            
                        except Exception as item_e:
                            logger.warning(f"HTTP方式处理单个快讯项时出错: {str(item_e)}")
                            continue
                    
                    logger.info(f"HTTP方式成功解析 {len(news_items)} 个快讯项")
                    return news_items
                    
        except Exception as e:
            logger.warning(f"HTTP方式获取第一财经快讯失败: {str(e)}")
            return []

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
            
    async def _fetch_news(self):
        """获取并解析新闻列表"""
        logger.info("开始从第一财经获取新闻")
        
        driver = None
        try:
            # 判断是否已有WebDriver实例
            if not self.driver:
                logger.info("创建新的WebDriver实例")
                self.driver = self._create_driver()
            
            # 检查WebDriver实例是否创建成功
            if not self.driver:
                logger.warning("WebDriver创建失败，尝试使用HTTP方式获取新闻")
                return await self._fetch_news_http()
            
            driver = self.driver
            
            # 记录当前系统和ChromeDriver信息（用于调试）
            logger.info(f"当前系统平台: {platform.system()}")
            logger.info(f"使用的ChromeDriver: {driver.capabilities.get('chrome', {}).get('chromedriverVersion', '未知')}")
            
            # 新闻列表URL
            url = self.config.get("list_url", "https://www.yicai.com/news/")
            logger.info(f"访问第一财经新闻列表页: {url}")
            
            # 使用异步超时控制防止页面加载过长时间
            try:
                # 使用asyncio.wait_for来设置异步超时
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, lambda: driver.get(url)
                    ),
                    timeout=self.config.get("selenium_timeout", 30)
                )
            except asyncio.TimeoutError:
                logger.warning("访问第一财经页面超时，尝试使用HTTP方式获取")
                return await self._fetch_news_http()
            except Exception as e:
                logger.warning(f"访问第一财经页面异常: {str(e)}")
                return await self._fetch_news_http()
            
            # 等待新闻列表元素加载
            try:
                # 使用显式等待等待新闻列表元素
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".m-list"))
                )
                logger.info("新闻列表元素加载完成")
            except Exception as e:
                logger.warning(f"等待新闻列表元素超时: {str(e)}")
                # 尝试检查页面状态
                try:
                    page_source = driver.page_source
                    if len(page_source) < 1000:
                        logger.warning(f"页面内容异常短，可能未正确加载，内容长度: {len(page_source)}")
                    elif "forbidden" in page_source.lower() or "请求被拒绝" in page_source:
                        logger.warning("访问被拒绝，可能触发了网站防爬虫机制")
                    elif "404" in page_source or "找不到页面" in page_source:
                        logger.warning("页面返回404错误")
                except Exception:
                    pass
                
                return await self._fetch_news_http()
            
            # 获取新闻列表
            news_items = []
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, ".m-list li")
                logger.info(f"找到 {len(elements)} 个新闻项")
                
                if not elements:
                    logger.warning("未找到任何新闻项，尝试使用HTTP方式获取")
                    return await self._fetch_news_http()
                
                for element in elements[:self.config.get("max_items", 20)]:
                    try:
                        # 提取新闻信息
                        title_element = element.find_element(By.CSS_SELECTOR, "a")
                        title = title_element.text.strip()
                        url = title_element.get_attribute("href")
                        
                        if not title or not url:
                            logger.debug("跳过标题或URL为空的新闻项")
                            continue
                        
                        # 提取摘要（如果有）
                        summary = ""
                        try:
                            summary_element = element.find_element(By.CSS_SELECTOR, ".text")
                            summary = summary_element.text.strip()
                        except Exception:
                            # 如果无法获取摘要，尝试使用标题作为摘要
                            summary = title
                        
                        # 提取图片URL（如果有）
                        image_element = element.find_element(By.CSS_SELECTOR, "img")
                        image_url = image_element.get_attribute("src", "") if image_element else ""
                        
                        # 提取发布时间（如果有）
                        published_at = datetime.now()
                        try:
                            time_element = element.find_element(By.CSS_SELECTOR, ".time")
                            time_text = time_element.text.strip()
                            
                            # 解析时间字符串
                            if "今天" in time_text:
                                # 今天的新闻，使用当前日期
                                today = datetime.now().date()
                                time_part = time_text.replace("今天", "").strip()
                                if ":" in time_part:
                                    hour, minute = map(int, time_part.split(":"))
                                    published_at = datetime.combine(today, time(hour, minute))
                            elif "月" in time_text and "日" in time_text:
                                # 格式如 "5月20日 14:30"
                                match = re.search(r"(\d+)月(\d+)日\s*(\d+):(\d+)", time_text)
                                if match:
                                    month, day, hour, minute = map(int, match.groups())
                                    year = datetime.now().year
                                    published_at = datetime(year, month, day, hour, minute)
                            
                            # 创建新闻项
                            news_item = {
                                "title": title,
                                "url": url,
                                "summary": summary,
                                "image_url": image_url,
                                "published_at": published_at.isoformat()
                            }
                            news_items.append(news_item)
                            
                        except Exception as e:
                            logger.debug(f"解析发布时间失败: {str(e)}")
                        
                    except Exception as item_e:
                        logger.warning(f"处理单个新闻项时出错: {str(item_e)}")
                        continue
                
                logger.info(f"成功解析 {len(news_items)} 个新闻项")
                
                if not news_items:
                    logger.warning("未能成功解析任何新闻项，尝试使用HTTP方式获取")
                    return await self._fetch_news_http()
                
                return news_items
                
            except Exception as e:
                logger.warning(f"解析新闻列表时出错: {str(e)}")
                return await self._fetch_news_http()
            
        except Exception as e:
            logger.warning(f"使用Selenium获取第一财经新闻失败: {str(e)}")
            # 尝试使用HTTP方式获取
            return await self._fetch_news_http()
            
        finally:
            # 不关闭driver，留给后续使用
            pass
            
    async def _fetch_news_http(self):
        """使用HTTP方式获取新闻（备用方法）"""
        logger.info("尝试使用HTTP方式获取第一财经新闻")
        
        try:
            url = self.config.get("list_url", "https://www.yicai.com/news/")
            
            # 使用aiohttp进行异步HTTP请求
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {
                    "User-Agent": random.choice(self.USER_AGENTS),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
                }
                
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.warning(f"HTTP请求返回状态码 {response.status}")
                        return []
                    
                    html = await response.text()
                    
                    # 使用BeautifulSoup解析HTML
                    soup = BeautifulSoup(html, "html.parser")
                    
                    # 查找新闻列表
                    news_list = soup.select(".m-list li")
                    logger.info(f"HTTP方式找到 {len(news_list)} 个新闻项")
                    
                    if not news_list:
                        logger.warning("HTTP方式未找到任何新闻项")
                        return []
                    
                    news_items = []
                    for item in news_list[:self.config.get("max_items", 20)]:
                        try:
                            # 提取标题和URL
                            title_element = item.select_one("a")
                            if not title_element:
                                continue
                                
                            title = title_element.get_text(strip=True)
                            url = title_element.get("href", "")
                            
                            if not url.startswith("http"):
                                # 修正相对URL
                                url = f"https://www.yicai.com{url}"
                                
                            # 提取摘要
                            summary_element = item.select_one(".text")
                            summary = summary_element.get_text(strip=True) if summary_element else title
                            
                            # 提取图片URL
                            image_element = item.select_one("img")
                            image_url = image_element.get("src", "") if image_element else ""
                            
                            # 提取发布时间
                            published_at = datetime.now()
                            time_element = item.select_one(".time")
                            if time_element:
                                time_text = time_element.get_text(strip=True)
                                # 与上面相同的时间解析逻辑
                                if "今天" in time_text:
                                    today = datetime.now().date()
                                    time_part = time_text.replace("今天", "").strip()
                                    if ":" in time_part:
                                        hour, minute = map(int, time_part.split(":"))
                                        published_at = datetime.combine(today, time(hour, minute))
                                elif "月" in time_text and "日" in time_text:
                                    match = re.search(r"(\d+)月(\d+)日\s*(\d+):(\d+)", time_text)
                                    if match:
                                        month, day, hour, minute = map(int, match.groups())
                                        year = datetime.now().year
                                        published_at = datetime(year, month, day, hour, minute)
                            
                            # 创建新闻项
                            news_item = {
                                "title": title,
                                "url": url,
                                "summary": summary,
                                "image_url": image_url,
                                "published_at": published_at.isoformat()
                            }
                            news_items.append(news_item)
                            
                        except Exception as item_e:
                            logger.warning(f"HTTP方式处理单个新闻项时出错: {str(item_e)}")
                            continue
                    
                    logger.info(f"HTTP方式成功解析 {len(news_items)} 个新闻项")
                    return news_items
                    
        except Exception as e:
            logger.warning(f"HTTP方式获取第一财经新闻失败: {str(e)}")
            return []