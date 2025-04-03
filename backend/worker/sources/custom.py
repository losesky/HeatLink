import logging
import datetime
import hashlib
import re
import json
import os
import random
import platform
import asyncio
import time
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

from worker.sources.web import WebNewsSource
from worker.sources.base import NewsItemModel
from worker.utils.http_client import http_client

logger = logging.getLogger(__name__)
DEBUG_MODE = os.environ.get("DEBUG", "0") == "1"


class CustomWebSource(WebNewsSource):
    """
    自定义网页新闻源适配器
    用于处理用户创建的自定义源
    
    特性:
    - 使用Selenium WebDriver从网站获取新闻数据
    - 使用CSS选择器定位和提取新闻元素
    - 提供详细的错误处理和调试信息
    - 支持无头模式和缓存机制
    """
    
    # 用户代理列表
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Edge/120.0.0.0"
    ]
    
    def __init__(
        self,
        source_id: str,
        name: str,
        url: str,
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "general",
        country: str = "global",
        language: str = "en",
        config: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        config = config or {}
        
        # 默认配置
        default_config = {
            "headers": {
                "User-Agent": random.choice(self.USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": f"{language},en-US;q=0.8,en;q=0.5",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            },
            # Selenium配置
            "use_selenium": True,  # 默认启用Selenium
            "selenium_timeout": 30,  # 页面加载超时时间（秒）
            "selenium_wait_time": 5,  # 等待元素出现的时间（秒）
            "headless": True,  # 无头模式
            # 重试配置
            "max_retries": 3,
            "retry_delay": 2,
            # 缓存配置
            "use_cache": True,
            "cache_ttl": cache_ttl,
            # 调试配置
            "save_debug_info": DEBUG_MODE,
            "debug_dir": "debug",
        }
        
        # 合并配置
        for key, value in default_config.items():
            if key not in config:
                config[key] = value
                
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
        
        # Selenium WebDriver 相关
        self._driver = None
        self._driver_pid = None
        
        # 缓存相关
        self._cache_ttl = cache_ttl
        self._cache_lock = asyncio.Lock()
        
        # 只在URL不为空时记录完整信息
        if self.url:
            logger.info(f"初始化自定义源 {self.name}，URL: {self.url}")
        else:
            logger.debug(f"初始化自定义源 {self.name}，URL: <未提供> - 将在使用时从数据库获取")
    
    def _create_driver(self):
        """
        创建并配置Selenium WebDriver
        """
        try:
            logger.debug("开始创建Chrome WebDriver实例")
            chrome_options = Options()
            
            # 设置无头模式
            if self.config.get("headless", True):
                logger.debug("启用无头模式")
                chrome_options.add_argument("--headless=new")
            
            # 设置用户代理
            user_agent = random.choice(self.USER_AGENTS)
            logger.debug(f"使用用户代理: {user_agent}")
            chrome_options.add_argument(f"--user-agent={user_agent}")
            
            # 设置窗口大小
            chrome_options.add_argument("--window-size=1920,1080")
            
            # 检测WSL环境 - 使用统一的配置
            if "microsoft" in platform.uname().release.lower() or os.name == 'nt':
                logger.info("检测到WSL/Windows环境，应用特殊配置")
                # WSL必须的参数
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
            
            # 禁用GPU加速
            chrome_options.add_argument("--disable-gpu")
            
            # 禁用扩展
            chrome_options.add_argument("--disable-extensions")
            
            # 禁用开发者工具
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            # 禁用自动化控制提示
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            
            # 启用JavaScript
            chrome_options.add_argument("--enable-javascript")
            
            # 设置语言
            chrome_options.add_argument(f"--lang={self.language}")
            
            # 尝试不同的ChromeDriver路径
            system = platform.system()
            if system == "Windows":
                chromedriver_paths = [
                    './chromedriver.exe',
                    'C:\\Program Files\\Google\\Chrome\\Application\\chromedriver.exe',
                    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chromedriver.exe'
                ]
            elif system == "Linux":
                chromedriver_paths = [
                    '/usr/local/bin/chromedriver',
                    '/usr/bin/chromedriver',
                    '/snap/bin/chromedriver',
                    './chromedriver'
                ]
            else:  # macOS
                chromedriver_paths = [
                    '/usr/local/bin/chromedriver',
                    '/usr/bin/chromedriver'
                ]
            
            # 查找可用的 ChromeDriver
            chromedriver_path = None
            for path in chromedriver_paths:
                if os.path.exists(path):
                    chromedriver_path = path
                    logger.info(f"找到ChromeDriver路径: {path}")
                    break
            
            if not chromedriver_path:
                chromedriver_path = "chromedriver"  # 使用 PATH 中的 ChromeDriver
                logger.info("使用系统PATH中的ChromeDriver")
                
            # 创建服务和驱动
            try:
                service = Service(executable_path=chromedriver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("成功创建Chrome WebDriver实例")
            except Exception as driver_e:
                logger.error(f"使用系统ChromeDriver失败: {str(driver_e)}")
                
                # 尝试使用webdriver_manager
                logger.info("尝试使用webdriver_manager...")
                
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("成功使用webdriver_manager创建WebDriver实例")
                
            # 设置页面加载超时
            driver.set_page_load_timeout(self.config.get("selenium_timeout", 30))
            
            # 设置脚本执行超时
            driver.set_script_timeout(self.config.get("selenium_timeout", 30))
            
            # 记录进程ID
            try:
                self._driver_pid = driver.service.process.pid
                logger.info(f"ChromeDriver进程ID: {self._driver_pid}")
            except Exception as e:
                logger.warning(f"无法获取ChromeDriver进程ID: {str(e)}")
            
            return driver
            
        except Exception as e:
            logger.error(f"创建WebDriver失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def _get_driver(self):
        """
        获取WebDriver实例，如果不存在则创建
        """
        if self._driver is None:
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
                logger.debug("正在关闭WebDriver")
                loop = asyncio.get_event_loop()
                
                # 首先尝试正常关闭
                try:
                    await loop.run_in_executor(None, self._driver.quit)
                    logger.debug("WebDriver已关闭")
                except Exception as e:
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
                                logger.debug(f"强制终止WebDriver进程 (PID: {self._driver_pid})")
                            except Exception as term_e:
                                logger.warning(f"终止WebDriver进程失败: {str(term_e)}")
                    except Exception:
                        pass
            finally:
                self._driver = None
                self._driver_pid = None
    
    async def save_debug_info(self, driver, prefix="debug"):
        """
        保存调试信息，包括屏幕截图和页面源代码
        
        Args:
            driver: WebDriver实例
            prefix: 文件名前缀
        """
        if not self.config.get("save_debug_info", False):
            return
        
        try:
            # 确保目录存在
            debug_dir = self.config.get("debug_dir", "debug")
            os.makedirs(debug_dir, exist_ok=True)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 保存屏幕截图
            screenshot_path = os.path.join(debug_dir, f"{prefix}_{self.source_id}_{timestamp}.png")
            logger.info(f"正在保存屏幕截图: {screenshot_path}")
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: driver.save_screenshot(screenshot_path)
            )
            
            # 保存页面源代码
            html_path = os.path.join(debug_dir, f"{prefix}_{self.source_id}_{timestamp}.html")
            logger.info(f"正在保存页面源代码: {html_path}")
            
            page_source = await loop.run_in_executor(
                None,
                lambda: driver.page_source
            )
            
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page_source)
            
            logger.info("调试信息已保存")
            
        except Exception as e:
            logger.error(f"保存调试信息失败: {str(e)}")
    
    async def close(self):
        """关闭资源"""
        # 关闭WebDriver
        if self._driver:
            try:
                await self._close_driver()
            except Exception as e:
                logger.error(f"关闭WebDriver时出错: {str(e)}")
        
        await super().close()
        
    async def fetch(self) -> List[NewsItemModel]:
        """
        获取新闻
        
        使用Selenium WebDriver获取页面内容并解析新闻数据
        
        Returns:
            新闻项列表
        """
        logger.info(f"开始获取 {self.name} 数据")
        try:
            start_time = time.time()
            
            try:
                # 实际获取新闻的实现
                news_items = await self._fetch_impl()
                logger.info(f"成功获取 {len(news_items) if news_items else 0} 条 {self.name} 数据，耗时 {time.time() - start_time:.2f} 秒")
                return news_items
                
            except Exception as e:
                logger.error(f"获取 {self.name} 数据失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return []
                
        except Exception as e:
            logger.error(f"执行 fetch 时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    async def _fetch_impl(self) -> List[NewsItemModel]:
        """
        获取新闻的实际实现
        
        Returns:
            新闻项列表
        """
        # Validate URL
        if not self.url:
            # 尝试从数据库获取URL
            db_url = await self._try_get_url_from_db()
            if db_url:
                logger.info(f"从数据库获取到URL: {db_url}")
                self.url = db_url
            else:
                logger.error(f"无法抓取 {self.source_id}：未提供URL且无法从数据库获取")
                return []
            
        # 检查URL格式
        if not self.url.startswith(('http://', 'https://')):
            logger.error(f"无效的URL格式: {self.url}，必须以http://或https://开头")
            return []
            
        # 记录使用的方式
        use_selenium = self.config.get("use_selenium", True)  # 默认为True
        logger.info(f"获取 {self.source_id} 数据，使用Selenium: {use_selenium}")
        
        # 存储页面调试信息
        self.page_debug = {}
        
        logger.info(f"开始使用Selenium获取 {self.source_id} 数据")
        logger.info(f"使用URL: {self.url}")
        
        # 获取选择器配置
        selectors = self.config.get("selectors", {})
        item_selector = selectors.get("item", "")
        title_selector = selectors.get("title", "")
        link_selector = selectors.get("link", "")
        date_selector = selectors.get("date", "")
        summary_selector = selectors.get("summary", "")
        content_selector = selectors.get("content", "")
        
        driver = await self._get_driver()
        if driver is None:
            logger.error("WebDriver创建失败")
            return []
        
        news_items = []
        try:
            # 访问页面
            logger.info(f"访问URL: {self.url}")
            loop = asyncio.get_event_loop()
            
            try:
                # 设置超时
                page_load_timeout = self.config.get("selenium_timeout", 30)
                await loop.run_in_executor(
                    None, 
                    lambda: driver.set_page_load_timeout(page_load_timeout)
                )
                
                # 访问URL
                await loop.run_in_executor(None, lambda: driver.get(self.url))
                
            except TimeoutException:
                logger.warning("页面加载超时，尝试继续解析已加载内容")
                await self.save_debug_info(driver, "timeout")
            except Exception as e:
                logger.error(f"页面加载失败: {str(e)}")
                await self.save_debug_info(driver, "error")
                return []
            
            # 等待页面加载完成
            try:
                # 等待页面主体加载
                await loop.run_in_executor(
                    None, 
                    lambda: WebDriverWait(driver, 5).until(
                        lambda d: d.execute_script("return document.readyState") == "complete"
                    )
                )
                logger.info("页面主体已加载")
            except:
                logger.warning("等待页面加载完成超时，尝试继续处理")
            
            # 执行滚动以加载更多内容
            logger.info("执行页面滚动以加载更多内容")
            for _ in range(3):  # 滚动三次
                try:
                    await loop.run_in_executor(
                        None,
                        lambda: driver.execute_script("window.scrollBy(0, window.innerHeight);")
                    )
                    await asyncio.sleep(0.5)  # 短暂等待加载
                except Exception as scroll_e:
                    logger.warning(f"滚动页面时出错: {str(scroll_e)}")
            
            # 从配置中获取选择器
            selectors = self.config.get("selectors", {})
            item_selector = selectors.get("item", "")
            title_selector = selectors.get("title", "")
            link_selector = selectors.get("link", "")
            date_selector = selectors.get("date", "")
            summary_selector = selectors.get("summary", "")
            content_selector = selectors.get("content", "")
            
            logger.info(f"使用选择器: 项目={item_selector}, 标题={title_selector}, 链接={link_selector}")
            
            if not item_selector or not title_selector:
                logger.error(f"缺少必要的选择器配置: 项目={item_selector}, 标题={title_selector}")
                await self.analyze_page_structure(driver, loop)
                return []
            
            # 等待项目容器元素加载
            try:
                logger.info(f"等待项目容器元素: {item_selector}")
                await loop.run_in_executor(
                    None,
                    lambda: WebDriverWait(driver, self.config.get("selenium_wait_time", 5)).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, item_selector))
                    )
                )
                logger.info("项目容器元素已找到")
            except Exception as wait_e:
                logger.warning(f"等待项目容器元素超时: {str(wait_e)}")
                await self.analyze_page_structure(driver, loop)
                # 继续尝试处理
            
            # 查找所有新闻项
            try:
                item_elements = await loop.run_in_executor(
                    None,
                    lambda: driver.find_elements(By.CSS_SELECTOR, item_selector)
                )
                logger.info(f"找到 {len(item_elements)} 个项目元素")
                
                # 如果没有找到任何项目，分析页面结构并返回
                if not item_elements:
                    logger.warning(f"未找到任何项目元素: {item_selector}")
                    await self.analyze_page_structure(driver, loop)
                    return []
                
                # 处理每个项目
                for index, item in enumerate(item_elements):
                    try:
                        # 提取标题
                        title_element = None
                        try:
                            title_element = await loop.run_in_executor(
                                None,
                                lambda: item.find_element(By.CSS_SELECTOR, title_selector)
                            )
                        except NoSuchElementException:
                            logger.warning(f"项目 {index} 中未找到标题元素: {title_selector}")
                            continue
                        
                        title = await loop.run_in_executor(
                            None,
                            lambda: title_element.text.strip()
                        )
                        
                        # 如果标题文本为空，尝试获取title属性
                        if not title:
                            title = await loop.run_in_executor(
                                None,
                                lambda: title_element.get_attribute('title')
                            )
                            
                        # 仍然为空，则跳过
                        if not title:
                            logger.warning(f"项目 {index} 的标题为空")
                            continue
                        
                        # 提取链接
                        link = ""
                        if link_selector:
                            try:
                                link_element = await loop.run_in_executor(
                                    None,
                                    lambda: item.find_element(By.CSS_SELECTOR, link_selector)
                                )
                                link = await loop.run_in_executor(
                                    None,
                                    lambda: link_element.get_attribute('href')
                                )
                            except NoSuchElementException:
                                # 如果找不到链接元素，尝试使用标题元素的href属性
                                link = await loop.run_in_executor(
                                    None,
                                    lambda: title_element.get_attribute('href')
                                )
                                if link:
                                    logger.info(f"项目 {index} 使用标题元素的href属性作为链接")
                        
                        # 如果没有找到链接，则使用主URL
                        if not link:
                            link = self.url
                            logger.warning(f"项目 {index} 没有链接，使用源URL")
                        
                        # 提取发布日期
                        published_at = datetime.datetime.now()
                        if date_selector:
                            try:
                                date_element = await loop.run_in_executor(
                                    None,
                                    lambda: item.find_element(By.CSS_SELECTOR, date_selector)
                                )
                                date_text = await loop.run_in_executor(
                                    None,
                                    lambda: date_element.text.strip()
                                )
                                if date_text:
                                    try:
                                        # 解析相对时间
                                        now = datetime.datetime.now()
                                        if "分钟前" in date_text:
                                            minutes_match = re.search(r'(\d+)\s*分钟前', date_text)
                                            if minutes_match:
                                                minutes = int(minutes_match.group(1))
                                                published_at = now - datetime.timedelta(minutes=minutes)
                                                logger.info(f"解析相对时间 '{date_text}' 为 {published_at}")
                                        elif "小时前" in date_text:
                                            hours_match = re.search(r'(\d+)\s*小时前', date_text)
                                            if hours_match:
                                                hours = int(hours_match.group(1))
                                                published_at = now - datetime.timedelta(hours=hours)
                                                logger.info(f"解析相对时间 '{date_text}' 为 {published_at}")
                                        elif "天前" in date_text:
                                            days_match = re.search(r'(\d+)\s*天前', date_text)
                                            if days_match:
                                                days = int(days_match.group(1))
                                                published_at = now - datetime.timedelta(days=days)
                                                logger.info(f"解析相对时间 '{date_text}' 为 {published_at}")
                                        elif "周前" in date_text:
                                            weeks_match = re.search(r'(\d+)\s*周前', date_text)
                                            if weeks_match:
                                                weeks = int(weeks_match.group(1))
                                                published_at = now - datetime.timedelta(weeks=weeks)
                                                logger.info(f"解析相对时间 '{date_text}' 为 {published_at}")
                                        elif "月前" in date_text:
                                            months_match = re.search(r'(\d+)\s*月前', date_text)
                                            if months_match:
                                                months = int(months_match.group(1))
                                                result = datetime.datetime(now.year, now.month, now.day, now.hour, now.minute, now.second)
                                                month = result.month - months
                                                year = result.year
                                                while month <= 0:
                                                    month += 12
                                                    year -= 1
                                                result = result.replace(year=year, month=month)
                                                published_at = result
                                                logger.info(f"解析相对时间 '{date_text}' 为 {published_at}")
                                        elif "年前" in date_text:
                                            years_match = re.search(r'(\d+)\s*年前', date_text)
                                            if years_match:
                                                years = int(years_match.group(1))
                                                published_at = now.replace(year=now.year - years)
                                                logger.info(f"解析相对时间 '{date_text}' 为 {published_at}")
                                        elif "昨天" in date_text:
                                            # 处理"昨天 12:34"格式
                                            time_match = re.search(r'昨天\s*(\d{1,2}):(\d{1,2})', date_text)
                                            if time_match:
                                                hour = int(time_match.group(1))
                                                minute = int(time_match.group(2))
                                                published_at = (now - datetime.timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
                                            else:
                                                # 没有具体时间的昨天
                                                published_at = (now - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                                            logger.info(f"解析相对时间 '{date_text}' 为 {published_at}")
                                        elif ":" in date_text:
                                            # 处理今天的时间格式 "12:34"
                                            if re.match(r'^\d{1,2}:\d{1,2}$', date_text):
                                                time_parts = date_text.split(':')
                                                hour = int(time_parts[0])
                                                minute = int(time_parts[1])
                                                published_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                                                logger.info(f"解析今天时间 '{date_text}' 为 {published_at}")
                                            # 处理完整日期时间格式 "2025-01-01 12:34"
                                            elif re.match(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{1,2}', date_text):
                                                try:
                                                    date_formats = [
                                                        '%Y-%m-%d %H:%M:%S',
                                                        '%Y-%m-%d %H:%M',
                                                        '%Y/%m/%d %H:%M:%S',
                                                        '%Y/%m/%d %H:%M'
                                                    ]
                                                    for fmt in date_formats:
                                                        try:
                                                            published_at = datetime.datetime.strptime(date_text, fmt)
                                                            break
                                                        except ValueError:
                                                            continue
                                                    logger.info(f"解析完整日期时间 '{date_text}' 为 {published_at}")
                                                except Exception as e:
                                                    logger.warning(f"解析完整日期时间 '{date_text}' 失败: {str(e)}")
                                    except Exception as date_e:
                                        logger.warning(f"解析日期时间 '{date_text}' 失败: {str(date_e)}")
                                        # 保持使用当前时间作为后备
                        
                        # 提取摘要
                        summary = ""
                        if summary_selector:
                            try:
                                summary_element = await loop.run_in_executor(
                                    None,
                                    lambda: item.find_element(By.CSS_SELECTOR, summary_selector)
                                )
                                summary = await loop.run_in_executor(
                                    None,
                                    lambda: summary_element.text.strip()
                                )
                            except NoSuchElementException:
                                logger.warning(f"项目 {index} 中未找到摘要元素: {summary_selector}")
                        
                        # 如果没有摘要，则使用标题
                        if not summary:
                            summary = title
                        
                        # 提取内容
                        content = ""
                        if content_selector:
                            try:
                                content_element = await loop.run_in_executor(
                                    None,
                                    lambda: item.find_element(By.CSS_SELECTOR, content_selector)
                                )
                                content = await loop.run_in_executor(
                                    None,
                                    lambda: content_element.text.strip()
                                )
                            except NoSuchElementException:
                                logger.warning(f"项目 {index} 中未找到内容元素: {content_selector}")
                        
                        # 如果没有内容，则使用摘要
                        if not content:
                            content = summary
                        
                        # 生成唯一ID
                        content_hash = f"{self.source_id}:{link}:{title}"
                        item_id = hashlib.md5(content_hash.encode()).hexdigest()
                        
                        # 创建新闻项目
                        news_item = NewsItemModel(
                            id=item_id,
                            title=title,
                            url=link,
                            source_id=self.source_id,
                            source_name=self.name,
                            content=content,
                            summary=summary,
                            published_at=published_at,
                            language=self.language,
                            country=self.country,
                            category=self.category,
                            extra={
                                "index": index,
                                "custom_source": True
                            }
                        )
                        
                        news_items.append(news_item)
                        logger.info(f"成功处理项目 {index}: {title}")
                        
                    except Exception as item_e:
                        logger.warning(f"处理项目 {index} 时出错: {str(item_e)}")
                        import traceback
                        logger.debug(traceback.format_exc())
                
            except Exception as find_e:
                logger.error(f"查找项目元素时出错: {str(find_e)}")
                import traceback
                logger.error(traceback.format_exc())
            
            # 如果无法通过Selenium提取，尝试从页面源码提取
            if not news_items:
                logger.warning("通过Selenium未提取到新闻，尝试从页面源码提取")
                
                # 获取页面源码
                page_source = await loop.run_in_executor(None, lambda: driver.page_source)
                
                # 使用BeautifulSoup解析
                try:
                    items = await self.parse_response(page_source)
                    if items:
                        logger.info(f"通过BeautifulSoup提取到 {len(items)} 条新闻")
                        news_items = items
                except Exception as bs_e:
                    logger.error(f"使用BeautifulSoup解析失败: {str(bs_e)}")
            
            logger.info(f"成功获取 {len(news_items)} 条 {self.name} 数据")
            return news_items
            
        except Exception as e:
            logger.error(f"获取 {self.name} 数据失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            await self.save_debug_info(driver, "error")
            return []
        finally:
            await self._close_driver()
    
    async def analyze_page_structure(self, driver, loop):
        """
        分析页面结构，提供调试信息
        
        Args:
            driver: WebDriver实例
            loop: 事件循环
        """
        logger.info("开始分析页面结构")
        
        try:
            # 获取页面源码
            page_source = await loop.run_in_executor(None, lambda: driver.page_source)
            
            # 使用BeautifulSoup解析
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # 记录页面的基本结构
            body = soup.find('body')
            if body:
                # 记录顶级元素及其类和ID
                first_level_elements = []
                for tag in body.find_all(recursive=False):
                    tag_info = {"name": tag.name}
                    if tag.get('class'):
                        tag_info["class"] = " ".join(tag.get('class'))
                    if tag.get('id'):
                        tag_info["id"] = tag.get('id')
                    first_level_elements.append(tag_info)
                
                logger.info(f"页面顶级元素: {first_level_elements}")
                
                # 提取一些常见的容器元素
                common_containers = []
                common_selectors = [
                    'div.container', 'div.content', 'main', 'article', 'section',
                    'div.list', 'div.news', 'div.articles', 'div.items', 'ul.list'
                ]
                for selector in common_selectors:
                    for container in body.select(selector):
                        container_info = {"name": container.name}
                        if container.get('class'):
                            container_info["class"] = " ".join(container.get('class'))
                        if container.get('id'):
                            container_info["id"] = container.get('id')
                        common_containers.append(container_info)
                
                if common_containers:
                    logger.info(f"常见容器元素: {common_containers}")
                
                # 尝试列出可能的列表元素
                potential_items = []
                
                # 查找可能的列表元素
                for list_tag in ['ul', 'ol', 'dl']:
                    list_elements = soup.find_all(list_tag)
                    if list_elements:
                        logger.info(f"发现 {len(list_elements)} 个 {list_tag} 元素")
                        for i, el in enumerate(list_elements[:3]):  # 只记录前3个
                            classes = " ".join(el.get('class', []))
                            id_attr = el.get('id', '')
                            child_count = len(el.find_all(recursive=False))
                            potential_items.append({
                                "类型": list_tag,
                                "索引": i,
                                "类": classes,
                                "ID": id_attr,
                                "子元素数": child_count,
                                "建议选择器": f"{list_tag}#{id_attr}" if id_attr else (f"{list_tag}.{classes.replace(' ', '.')}" if classes else list_tag)
                            })
                
                # 查找具有多个相似子元素的div容器
                div_containers = soup.find_all('div')
                for div in div_containers:
                    children = div.find_all(recursive=False)
                    if len(children) >= 3:  # 至少有3个子元素才可能是列表容器
                        # 检查子元素是否相似（相同标签名）
                        child_tags = [child.name for child in children]
                        if len(set(child_tags)) <= 3:  # 最多3种不同标签
                            classes = " ".join(div.get('class', []))
                            id_attr = div.get('id', '')
                            potential_items.append({
                                "类型": "div",
                                "索引": len(potential_items),
                                "类": classes,
                                "ID": id_attr,
                                "子元素数": len(children),
                                "子元素类型": list(set(child_tags)),
                                "建议选择器": f"div#{id_attr}" if id_attr else (f"div.{classes.replace(' ', '.')}" if classes else "div")
                            })
                
                # 查找可能的文章元素
                articles = soup.find_all('article')
                if articles:
                    logger.info(f"发现 {len(articles)} 个 article 元素")
                    for i, article in enumerate(articles[:3]):
                        classes = " ".join(article.get('class', []))
                        id_attr = article.get('id', '')
                        potential_items.append({
                            "类型": "article",
                            "索引": i,
                            "类": classes,
                            "ID": id_attr,
                            "建议选择器": f"article#{id_attr}" if id_attr else (f"article.{classes.replace(' ', '.')}" if classes else "article")
                        })
                
                if potential_items:
                    logger.info(f"发现潜在的项目容器: {potential_items}")
                    logger.info(f"建议: 尝试使用这些选择器之一作为项目选择器，并使用适当的子选择器来获取标题和链接")
                
                # 记录页面中所有的标题和链接元素
                headlines = []
                for h_tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    h_elements = soup.find_all(h_tag)
                    if h_elements:
                        for i, el in enumerate(h_elements[:5]):  # 只记录前5个
                            parent_class = " ".join(el.parent.get('class', []))
                            parent_id = el.parent.get('id', '')
                            headlines.append({
                                "类型": h_tag,
                                "文本": el.get_text(strip=True)[:30] + ('...' if len(el.get_text(strip=True)) > 30 else ''),
                                "父元素": el.parent.name,
                                "父元素类": parent_class,
                                "父元素ID": parent_id,
                                "建议标题选择器": f"{h_tag}"
                            })
                
                links = []
                a_elements = soup.find_all('a', href=True)
                if a_elements:
                    for i, el in enumerate(a_elements[:5]):  # 只记录前5个
                        parent_class = " ".join(el.parent.get('class', []))
                        parent_id = el.parent.get('id', '')
                        links.append({
                            "类型": "a",
                            "文本": el.get_text(strip=True)[:30] + ('...' if len(el.get_text(strip=True)) > 30 else ''),
                            "链接": el['href'][:50] + ('...' if len(el['href']) > 50 else ''),
                            "父元素": el.parent.name,
                            "父元素类": parent_class,
                            "父元素ID": parent_id,
                            "建议链接选择器": f"a"
                        })
                
                if headlines:
                    logger.info(f"页面中的标题元素: {headlines}")
                
                if links:
                    logger.info(f"页面中的链接元素: {links}")
            
            # 保存页面源码以便进一步分析
            await self.save_debug_info(driver, "analysis")
            
        except Exception as e:
            logger.error(f"分析页面结构时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    async def parse_response(self, html: str) -> List[NewsItemModel]:
        """
        解析HTML响应，提取新闻项目
        
        用于从HTML字符串解析新闻项目，作为Selenium方法的备用
        
        Args:
            html: HTML内容
            
        Returns:
            List[NewsItemModel]: 新闻项目列表
        """
        news_items = []
        
        try:
            # 记录HTML长度
            html_length = len(html) if html else 0
            logger.info(f"解析HTML内容，长度: {html_length}")
            
            if not html or html_length < 100:
                logger.warning(f"获取的HTML内容太短或为空，无法解析")
                return []
                
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(html, 'html.parser')
            
            # 从配置中获取选择器
            selectors = self.config.get("selectors", {})
            item_selector = selectors.get("item", "")
            title_selector = selectors.get("title", "")
            link_selector = selectors.get("link", "")
            date_selector = selectors.get("date", "")
            summary_selector = selectors.get("summary", "")
            content_selector = selectors.get("content", "")
            
            logger.info(f"使用选择器: 项目={item_selector}, 标题={title_selector}, 链接={link_selector}")
            
            if not item_selector or not title_selector:
                logger.error(f"缺少必要的选择器配置")
                return []
            
            # 找到所有新闻项目
            items = soup.select(item_selector)
            logger.info(f"找到 {len(items)} 个项目")
            
            # 如果没有找到任何项目，尝试记录页面结构以便调试
            if not items or len(items) == 0:
                logger.warning(f"未找到任何项目")
                return []
            
            # 处理每个项目
            for index, item in enumerate(items):
                try:
                    # 提取标题
                    title_element = item.select_one(title_selector)
                    if not title_element:
                        logger.warning(f"项目 {index} 没有标题元素")
                        continue
                            
                    title = title_element.get_text(strip=True)
                    
                    # 提取链接
                    link = ""
                    if link_selector:
                        link_element = item.select_one(link_selector)
                        if link_element and link_element.has_attr('href'):
                            link = link_element['href']
                                
                            # 将相对URL转换为绝对URL
                            if link and not link.startswith(('http://', 'https://')):
                                link = urljoin(self.url, link)
                    else:
                        # 如果没有指定链接选择器，尝试使用标题元素的链接
                        if title_element.name == 'a' and title_element.has_attr('href'):
                            link = title_element['href']
                            # 将相对URL转换为绝对URL
                            if link and not link.startswith(('http://', 'https://')):
                                link = urljoin(self.url, link)
                    
                    # 如果没有找到链接，则使用主URL
                    if not link:
                        link = self.url
                    
                    # 提取发布日期
                    published_at = datetime.datetime.now()
                    if date_selector:
                        date_element = item.select_one(date_selector)
                        if date_element:
                            date_text = date_element.get_text(strip=True)
                            if date_text:
                                try:
                                    # 解析相对时间
                                    now = datetime.datetime.now()
                                    if "分钟前" in date_text:
                                        minutes_match = re.search(r'(\d+)\s*分钟前', date_text)
                                        if minutes_match:
                                            minutes = int(minutes_match.group(1))
                                            published_at = now - datetime.timedelta(minutes=minutes)
                                            logger.info(f"解析相对时间 '{date_text}' 为 {published_at}")
                                    elif "小时前" in date_text:
                                        hours_match = re.search(r'(\d+)\s*小时前', date_text)
                                        if hours_match:
                                            hours = int(hours_match.group(1))
                                            published_at = now - datetime.timedelta(hours=hours)
                                            logger.info(f"解析相对时间 '{date_text}' 为 {published_at}")
                                    elif "天前" in date_text:
                                        days_match = re.search(r'(\d+)\s*天前', date_text)
                                        if days_match:
                                            days = int(days_match.group(1))
                                            published_at = now - datetime.timedelta(days=days)
                                            logger.info(f"解析相对时间 '{date_text}' 为 {published_at}")
                                    elif "周前" in date_text:
                                        weeks_match = re.search(r'(\d+)\s*周前', date_text)
                                        if weeks_match:
                                            weeks = int(weeks_match.group(1))
                                            published_at = now - datetime.timedelta(weeks=weeks)
                                            logger.info(f"解析相对时间 '{date_text}' 为 {published_at}")
                                    elif "月前" in date_text:
                                        months_match = re.search(r'(\d+)\s*月前', date_text)
                                        if months_match:
                                            months = int(months_match.group(1))
                                            result = datetime.datetime(now.year, now.month, now.day, now.hour, now.minute, now.second)
                                            month = result.month - months
                                            year = result.year
                                            while month <= 0:
                                                month += 12
                                                year -= 1
                                            result = result.replace(year=year, month=month)
                                            published_at = result
                                            logger.info(f"解析相对时间 '{date_text}' 为 {published_at}")
                                    elif "年前" in date_text:
                                        years_match = re.search(r'(\d+)\s*年前', date_text)
                                        if years_match:
                                            years = int(years_match.group(1))
                                            published_at = now.replace(year=now.year - years)
                                            logger.info(f"解析相对时间 '{date_text}' 为 {published_at}")
                                    elif "昨天" in date_text:
                                        # 处理"昨天 12:34"格式
                                        time_match = re.search(r'昨天\s*(\d{1,2}):(\d{1,2})', date_text)
                                        if time_match:
                                            hour = int(time_match.group(1))
                                            minute = int(time_match.group(2))
                                            published_at = (now - datetime.timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
                                        else:
                                            # 没有具体时间的昨天
                                            published_at = (now - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                                        logger.info(f"解析相对时间 '{date_text}' 为 {published_at}")
                                    elif ":" in date_text:
                                        # 处理今天的时间格式 "12:34"
                                        if re.match(r'^\d{1,2}:\d{1,2}$', date_text):
                                            time_parts = date_text.split(':')
                                            hour = int(time_parts[0])
                                            minute = int(time_parts[1])
                                            published_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                                            logger.info(f"解析今天时间 '{date_text}' 为 {published_at}")
                                        # 处理完整日期时间格式 "2025-01-01 12:34"
                                        elif re.match(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{1,2}', date_text):
                                            try:
                                                date_formats = [
                                                    '%Y-%m-%d %H:%M:%S',
                                                    '%Y-%m-%d %H:%M',
                                                    '%Y/%m/%d %H:%M:%S',
                                                    '%Y/%m/%d %H:%M'
                                                ]
                                                for fmt in date_formats:
                                                    try:
                                                        published_at = datetime.datetime.strptime(date_text, fmt)
                                                        break
                                                    except ValueError:
                                                        continue
                                                logger.info(f"解析完整日期时间 '{date_text}' 为 {published_at}")
                                            except Exception as e:
                                                logger.warning(f"解析完整日期时间 '{date_text}' 失败: {str(e)}")
                                except Exception as date_e:
                                    logger.warning(f"解析日期时间 '{date_text}' 失败: {str(date_e)}")
                                    # 保持使用当前时间作为后备
                        
                    # 提取摘要
                    summary = ""
                    if summary_selector:
                        summary_element = item.select_one(summary_selector)
                        if summary_element:
                            summary = summary_element.get_text(strip=True)
                    
                    # 如果没有摘要，则使用标题
                    if not summary:
                        summary = title
                    
                    # 提取内容
                    content = ""
                    if content_selector:
                        content_element = item.select_one(content_selector)
                        if content_element:
                            content = content_element.get_text(strip=True)
                    
                    # 如果没有内容，则使用摘要
                    if not content:
                        content = summary
                    
                    # 生成唯一ID
                    content_hash = f"{self.source_id}:{link}:{title}"
                    item_id = hashlib.md5(content_hash.encode()).hexdigest()
                    
                    # 创建新闻项目
                    news_item = NewsItemModel(
                        id=item_id,
                        title=title,
                        url=link,
                        source_id=self.source_id,
                        source_name=self.name,
                        content=content,
                        summary=summary,
                        published_at=published_at,
                        language=self.language,
                        country=self.country,
                        category=self.category,
                        extra={
                            "index": index,
                            "custom_source": True
                        }
                    )
                    
                    news_items.append(news_item)
                    
                except Exception as e:
                    logger.warning(f"处理项目 {index} 时出错: {str(e)}")
        
        except Exception as e:
            logger.error(f"解析响应时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        
        logger.info(f"成功解析 {len(news_items)} 个新闻项目")
        return news_items 

    async def _try_get_url_from_db(self) -> Optional[str]:
        """尝试从数据库获取URL"""
        try:
            # 仅当source_id以custom-开头时尝试
            if not self.source_id.startswith('custom-'):
                return None
                
            # 导入所需模块
            try:
                import sys
                import os
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                sys.path.insert(0, base_dir)
                
                from app.db.session import SessionLocal
                from sqlalchemy import text
                
                # 创建数据库会话
                db = SessionLocal()
                try:
                    # 查询数据库
                    sql = "SELECT url FROM sources WHERE id = :id"
                    result = db.execute(text(sql), {"id": self.source_id})
                    row = result.fetchone()
                    if row and row[0]:
                        return row[0]
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"从数据库获取URL时出错: {str(e)}")
                
            return None
        except Exception as e:
            logger.error(f"尝试获取URL时出错: {str(e)}")
            return None 