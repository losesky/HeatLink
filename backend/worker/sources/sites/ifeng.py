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
from pathlib import Path

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


class IfengBaseSource(WebNewsSource):
    """
    凤凰网新闻适配器基类
    可以获取凤凰网站的新闻内容
    
    特性:
    - 使用Selenium WebDriver从网站获取新闻数据
    - 支持获取不同板块的内容
    - 使用缓存机制减少请求频率
    - 提供错误处理和重试机制
    """
    
    # 用户代理列表
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Edge/120.0.0.0"
    ]
    
    # 凤凰网主域名
    BASE_URL = "https://www.ifeng.com/"
    
    def __init__(
        self,
        source_id: str,
        name: str,
        url: str,
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "news",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        
        # 默认配置
        default_config = {
            "headers": {
                "User-Agent": random.choice(self.USER_AGENTS),
                "Referer": self.BASE_URL,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            },
            # Selenium配置
            "use_selenium": True,  # 启用Selenium
            "selenium_timeout": 30,  # 页面加载超时时间（秒）
            "selenium_wait_time": 5,  # 等待元素出现的时间（秒）
            "headless": True,  # 无头模式
            # 重试配置
            "max_retries": 3,
            "retry_delay": 2,
            # 启用缓存
            "use_cache": True,
            "cache_ttl": cache_ttl,
            # 启用随机延迟
            "use_random_delay": True,
            "min_delay": 0.5,
            "max_delay": 1.5,
            # 整体超时控制
            "overall_timeout": 60,  # 整体操作超时时间（秒）
            # HTTP备用方式
            "use_http_fallback": True,
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
        
        # HTTP备用标志
        self._tried_http_fallback = False
        
        logger.info(f"初始化 {self.name} 适配器，URL: {self.url}")
    
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
            
            # 设置唯一的用户数据目录，避免"user data directory is already in use"错误
            unique_dir = f"/tmp/chrome_data_dir_{time.time()}_{random.randint(1, 10000)}"
            chrome_options.add_argument(f"--user-data-dir={unique_dir}")
            logger.debug(f"设置唯一用户数据目录: {unique_dir}")
            
            # 检测WSL环境 - 使用统一的配置
            if "microsoft" in platform.uname().release.lower() or "Microsoft" in os.uname().release:
                logger.info("检测到WSL环境，应用特殊配置")
                # WSL必须的参数
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
            
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
                    '/home/losesky/HeatLink/chromedriver'
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
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析响应内容
        这是基类的方法，子类应该重写此方法来解析特定板块的内容
        
        Args:
            response: 网页响应内容
            
        Returns:
            解析后的新闻项列表
        """
        logger.warning(f"{self.__class__.__name__}.parse_response被直接调用，这通常不是预期行为。子类应该重写此方法。")
        return []
    
    def extract_date(self, date_str: str) -> Optional[datetime.datetime]:
        """
        从日期字符串解析出时间
        
        支持的格式:
        - 2025-03-31 10:46:28
        - 10:46
        - 3分钟前
        - 昨天 10:46
        - 03-31 10:46
        - 今天 10:46
        - 昨天 10:46
        
        Args:
            date_str: 日期字符串
        
        Returns:
            解析后的datetime对象，如果无法解析则返回None
        """
        if not date_str:
            return None
            
        try:
            date_str = date_str.strip()
            now = datetime.datetime.now()
            
            # 直接匹配完整的日期时间格式
            if re.match(r'\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{1,2}(:\d{1,2})?', date_str):
                # 格式如：2025-03-31 10:46:28 或 2025-03-31 10:46
                try:
                    if date_str.count(':') == 2:
                        # 包含秒
                        return datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                    else:
                        # 不包含秒
                        return datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M')
                except Exception as e:
                    logger.warning(f"解析完整日期时间格式失败: {date_str}, 错误: {str(e)}")
            
            # 匹配只有时间的格式 (如 10:46 或 10:46:28)
            elif re.match(r'^\d{1,2}:\d{1,2}(:\d{1,2})?$', date_str):
                try:
                    time_parts = date_str.split(':')
                    if len(time_parts) == 2:
                        hour, minute = map(int, time_parts)
                        return datetime.datetime.combine(now.date(), datetime.time(hour, minute))
                    elif len(time_parts) == 3:
                        hour, minute, second = map(int, time_parts)
                        return datetime.datetime.combine(now.date(), datetime.time(hour, minute, second))
                except Exception as e:
                    logger.warning(f"解析时间格式失败: {date_str}, 错误: {str(e)}")
            
            # 匹配"X分钟前"或"X小时前"的格式
            elif re.match(r'(\d+)分钟前', date_str):
                minutes = int(re.match(r'(\d+)分钟前', date_str).group(1))
                return now - datetime.timedelta(minutes=minutes)
            elif re.match(r'(\d+)小时前', date_str):
                hours = int(re.match(r'(\d+)小时前', date_str).group(1))
                return now - datetime.timedelta(hours=hours)
            
            # 匹配"昨天 XX:XX"格式
            elif date_str.startswith('昨天'):
                time_str = date_str.replace('昨天', '').strip()
                try:
                    if ':' in time_str:
                        hour, minute = map(int, time_str.split(':'))
                        yesterday = now - datetime.timedelta(days=1)
                        return datetime.datetime.combine(yesterday.date(), datetime.time(hour, minute))
                except Exception as e:
                    logger.warning(f"解析'昨天'格式失败: {date_str}, 错误: {str(e)}")
            
            # 匹配"今天 XX:XX"格式
            elif date_str.startswith('今天'):
                time_str = date_str.replace('今天', '').strip()
                try:
                    if ':' in time_str:
                        hour, minute = map(int, time_str.split(':'))
                        return datetime.datetime.combine(now.date(), datetime.time(hour, minute))
                except Exception as e:
                    logger.warning(f"解析'今天'格式失败: {date_str}, 错误: {str(e)}")
            
            # 匹配"MM-DD XX:XX"格式
            elif re.match(r'\d{1,2}-\d{1,2}\s+\d{1,2}:\d{1,2}', date_str):
                try:
                    date_part, time_part = date_str.split()
                    month, day = map(int, date_part.split('-'))
                    hour, minute = map(int, time_part.split(':'))
                    
                    # 假设是当前年份，除非解析出的日期在未来
                    year = now.year
                    parsed_date = datetime.datetime(year, month, day, hour, minute)
                    
                    # 如果解析出的日期在未来超过1天，则可能是去年的日期
                    if (parsed_date - now).days > 1:
                        parsed_date = datetime.datetime(year - 1, month, day, hour, minute)
                    
                    return parsed_date
                except Exception as e:
                    logger.warning(f"解析'MM-DD XX:XX'格式失败: {date_str}, 错误: {str(e)}")
            
            # 无法匹配任何格式
            logger.warning(f"无法识别的日期格式: {date_str}")
            return now
            
        except Exception as e:
            logger.error(f"解析日期出错: {date_str}, 错误: {str(e)}")
            return now
    
    def generate_id(self, url: str, title: str) -> str:
        """
        根据URL和标题生成唯一ID
        
        Args:
            url: 新闻URL
            title: 新闻标题
            
        Returns:
            唯一标识ID
        """
        content = f"{self.source_id}:{url}:{title}"
        return hashlib.md5(content.encode()).hexdigest()
    
    async def _fetch_with_http_fallback(self) -> List[NewsItemModel]:
        """
        当Selenium方法失败时，使用HTTP请求作为备用方案
        """
        logger.info(f"使用HTTP备用方法获取数据: {self.url}")
        
        # 设置标志
        self._tried_http_fallback = True
        start_time = datetime.datetime.now()
        
        try:
            # 准备请求头 - 随机选择用户代理
            headers = {
                "User-Agent": random.choice(self.USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": self.BASE_URL,
                "Connection": "keep-alive",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Upgrade-Insecure-Requests": "1"
            }
            
            # 记录请求信息
            logger.info(f"HTTP备用请求: GET {self.url}, UA: {headers['User-Agent'][:20]}...")
            
            # 使用aiohttp进行异步请求
            async with aiohttp.ClientSession(headers=headers) as session:
                try:
                    # 增加超时设置
                    async with session.get(self.url, timeout=30) as response:
                        if response.status != 200:
                            logger.error(f"HTTP请求失败，状态码: {response.status}")
                            return []
                        
                        # 获取文本内容
                        content = await response.text()
                        
                        if not content or len(content) < 500:
                            logger.error(f"HTTP响应内容太少，长度仅 {len(content)} 字符")
                            return []
                        
                        logger.info(f"成功获取HTTP响应，长度: {len(content)} 字符")
                        
                        # 解析内容
                        items = await self.parse_response(content)
                        
                        # 记录请求用时
                        elapsed = (datetime.datetime.now() - start_time).total_seconds()
                        logger.info(f"HTTP备用方法用时: {elapsed:.2f}秒，获取到 {len(items)} 条新闻")
                        
                        return items
                        
                except asyncio.TimeoutError:
                    logger.error("HTTP请求超时")
                    return []
                except Exception as req_e:
                    logger.error(f"HTTP请求过程中出错: {str(req_e)}")
                    return []
        except Exception as e:
            logger.error(f"HTTP备用方法失败: {str(e)}")
            return []
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        获取新闻
        
        Returns:
            新闻项列表
        """
        logger.info(f"开始获取 {self.name} 数据")
        try:
            start_time = time.time()
            
            try:
                # 实际获取新闻的实现，调用_fetch_impl
                news_items = await self._fetch_impl()
                logger.info(f"成功获取 {len(news_items) if news_items else 0} 条 {self.name} 数据，耗时 {time.time() - start_time:.2f} 秒")
                
                # 注意：这里不再手动更新缓存
                # 缓存更新由基类的get_news方法负责
                
                return news_items
                
            except Exception as e:
                logger.error(f"获取 {self.name} 数据时出错: {str(e)}", exc_info=True)
                
                # HTTP备用获取
                if self.config.get("use_http_fallback", False) and not self._tried_http_fallback:
                    logger.warning(f"尝试使用HTTP备用方式获取 {self.name} 数据")
                    self._tried_http_fallback = True
                    try:
                        news_items = await self._fetch_with_http_fallback()
                        if news_items:
                            logger.info(f"使用HTTP备用方式成功获取 {len(news_items)} 条 {self.name} 数据")
                            return news_items
                    except Exception as fallback_e:
                        logger.error(f"HTTP备用获取 {self.name} 数据失败: {str(fallback_e)}")
                
                # 如果备用方式也失败，且有缓存，可以在这记录失败但不操作缓存
                # 缓存保护由基类的get_news方法负责
                if hasattr(self, '_cached_news_items') and self._cached_news_items:
                    logger.warning(f"获取 {self.name} 数据失败，记录错误但不修改缓存")
                
                # 错误记录放这里，但让基类处理缓存保护
                raise e
                
        finally:
            # 重置HTTP备用标志
            self._tried_http_fallback = False
            
            # 如果有错误，不在这里处理缓存，让基类的get_news方法负责处理
        
        return []
    
    async def _fetch_impl(self) -> List[NewsItemModel]:
        """
        实际的获取数据实现
        子类必须重写此方法
        
        Returns:
            获取到的新闻项列表
        """
        raise NotImplementedError("子类必须实现_fetch_impl方法")
    
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
    
    async def clear_cache(self) -> None:
        """清理缓存数据"""
        async with self._cache_lock:
            self._cached_news_items = []
            self._last_cache_update = 0
        logger.info(f"已清理{self.name}缓存")
    
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

    def is_cache_valid(self) -> bool:
        """
        检查缓存是否有效
        
        Returns:
            bool: 缓存是否有效
        """
        if not self.config.get("use_cache", True):
            logger.info(f"[IFENG-CACHE-DEBUG] {self.source_id}: 配置禁用缓存，直接返回False")
            return False
            
        has_cached_items = bool(self._cached_news_items)
        cache_age = time.time() - self._last_cache_update if self._last_cache_update > 0 else float('inf')
        
        # 增强缓存有效期检查逻辑 - 针对特定源应用额外灵活的规则
        if self.source_id in ["ifeng-tech", "ifeng-studio"]:
            # 对于凤凰科技和凤凰工作室源，延长缓存有效期
            # 只要缓存年龄不超过配置的TTL的1.5倍，就认为有效
            cache_ttl_valid = cache_age < (self._cache_ttl * 1.5)
            logger.info(f"[IFENG-CACHE-DEBUG] {self.source_id}: 应用增强的缓存TTL检查 (1.5倍TTL)")
        else:
            # 标准TTL检查
            cache_ttl_valid = cache_age < self._cache_ttl
        
        logger.info(f"[IFENG-CACHE-DEBUG] {self.source_id}: 缓存状态检查")
        logger.info(f"[IFENG-CACHE-DEBUG] {self.source_id}: _cached_news_items={'有' if has_cached_items else '无'}, 条目数={len(self._cached_news_items) if self._cached_news_items else 0}")
        logger.info(f"[IFENG-CACHE-DEBUG] {self.source_id}: _last_cache_update={self._last_cache_update}, 缓存年龄={cache_age:.2f}秒")
        logger.info(f"[IFENG-CACHE-DEBUG] {self.source_id}: _cache_ttl={self._cache_ttl}秒, 是否未过期={cache_ttl_valid}")
        
        # 针对特定源的额外检查
        if self.source_id in ["ifeng-tech", "ifeng-studio"] and has_cached_items:
            # 即使缓存过期，如果内容丰富(超过5条)，仍然可以考虑有效以防止频繁获取失败
            # 但前提是缓存年龄不超过TTL的3倍(极端保护)
            if len(self._cached_news_items) > 5 and cache_age < (self._cache_ttl * 3):
                extreme_protection = True
                logger.warning(f"[IFENG-CACHE-PROTECTION] {self.source_id}: 启用极端缓存保护! 缓存年龄: {cache_age:.2f}秒, 但内容丰富({len(self._cached_news_items)}条)")
            else:
                extreme_protection = False
        else:
            extreme_protection = False
        
        # 标准判断 + 极端保护
        cache_valid = (has_cached_items and cache_ttl_valid) or extreme_protection
        logger.info(f"[IFENG-CACHE-DEBUG] {self.source_id}: 最终缓存有效性={cache_valid}, 极端保护={extreme_protection}")
        
        return cache_valid
    
    async def update_cache(self, news_items: List[NewsItemModel]) -> None:
        """
        更新缓存
        
        Args:
            news_items: 新闻项列表
        """
        logger.info(f"[IFENG-CACHE-DEBUG] {self.source_id}: 开始更新缓存，新闻条目数={len(news_items) if news_items else 0}")
        logger.info(f"[IFENG-CACHE-DEBUG] {self.source_id}: 缓存前状态: _cached_news_items条目数={len(self._cached_news_items) if self._cached_news_items else 0}, _last_cache_update={self._last_cache_update}")
        
        # 增强的缓存保护逻辑
        has_existing_cache = bool(self._cached_news_items)
        existing_items_count = len(self._cached_news_items) if self._cached_news_items else 0
        new_items_count = len(news_items) if news_items else 0
        
        # 情况1: 如果news_items为空且已有缓存，保留现有缓存
        if not news_items and has_existing_cache:
            logger.warning(f"[IFENG-CACHE-PROTECTION] {self.source_id}: 新闻条目为空，保留现有缓存({existing_items_count}条)，不更新")
            return
        
        # 情况2: 如果新抓取的内容明显少于现有缓存（减少50%以上），且现有缓存足够丰富（超过5条），保留现有缓存
        if has_existing_cache and existing_items_count > 5 and new_items_count > 0:
            # 计算减少率
            reduction_rate = (existing_items_count - new_items_count) / existing_items_count
            
            if reduction_rate > 0.5:  # 减少超过50%
                # 适用于特定源的更强保护
                if self.source_id in ["ifeng-tech", "ifeng-studio"]:
                    logger.warning(f"[IFENG-CACHE-PROTECTION] {self.source_id}: 新闻条目数显著减少 ({existing_items_count} -> {new_items_count}, 减少{reduction_rate:.1%})，保留现有缓存")
                    # 记录保护事件
                    protection_event = {
                        "time": time.time(),
                        "type": "content_reduction",
                        "old_count": existing_items_count,
                        "new_count": new_items_count,
                        "reduction_rate": reduction_rate
                    }
                    # 如果有保护统计字段则更新
                    if hasattr(self, '_cache_protection_stats'):
                        self._cache_protection_stats["shrink_protection_count"] = self._cache_protection_stats.get("shrink_protection_count", 0) + 1
                        if "protection_history" in self._cache_protection_stats:
                            self._cache_protection_stats["protection_history"].append(protection_event)
                    return
        
        # 标准更新流程
        async with self._cache_lock:
            self._cached_news_items = news_items
            self._last_cache_update = time.time()
            
        logger.info(f"[IFENG-CACHE-DEBUG] {self.source_id}: 缓存已更新，新状态: _cached_news_items条目数={len(self._cached_news_items) if self._cached_news_items else 0}, _last_cache_update={self._last_cache_update}")
        logger.debug(f"更新 {self.source_id} 缓存，共 {len(news_items)} 条数据")


class IfengStudioSource(IfengBaseSource):
    """
    凤凰财经全球快报适配器
    获取凤凰财经工作室全球快报内容
    使用Selenium WebDriver获取快讯列表
    """
    
    def __init__(
        self,
        source_id: str = "ifeng-studio",
        name: str = "凤凰财经全球快报",
        url: str = "https://finance.ifeng.com/studio",
        update_interval: int = 900,  # 15分钟更新一次，财经快讯更新频繁
        cache_ttl: int = 900,  # 15分钟缓存有效期，与更新间隔相同
        category: str = "finance",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        # 配置特定设置
        config = config or {}
        config.update({
            # 设置合理的超时时间
            "selenium_timeout": 40,  # 适当增加超时时间
            # 调试配置
            "save_debug_info": DEBUG_MODE,
            # HTTP备用
            "use_http_fallback": True,
            # 强制启用缓存
            "use_cache": True,
        })
        
        # 强制统一source_id
        if source_id != "ifeng-studio":
            logger.warning(f"源ID '{source_id}' 被统一为标准ID 'ifeng-studio'")
            source_id = "ifeng-studio"
            
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
        """
        使用Selenium获取凤凰财经工作室快讯
        """
        logger.info("开始获取凤凰财经全球快报快讯")
        driver = await self._get_driver()
        if driver is None:
            logger.error("WebDriver创建失败")
            return []
        
        news_items = []
        try:
            # 访问快讯页面
            logger.info(f"访问快讯URL: {self.url}")
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
            scroll_script = """
            function smoothScroll() {
                return new Promise((resolve) => {
                    let totalHeight = 0;
                    let distance = 300;
                    let scrolls = 0;
                    let maxScrolls = 10;
                    
                    let timer = setInterval(() => {
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        scrolls++;
                        
                        if(scrolls >= maxScrolls) {
                            clearInterval(timer);
                            resolve("滚动完成");
                        }
                    }, 100);
                });
            }
            return smoothScroll();
            """
            try:
                scroll_result = await loop.run_in_executor(
                    None, 
                    lambda: driver.execute_script(scroll_script)
                )
                logger.info(f"滚动结果: {scroll_result}")
            except:
                logger.warning("执行滚动脚本失败")
            
            # 等待动态内容加载
            await asyncio.sleep(2)
            
            # 等待快讯容器元素加载
            try:
                await loop.run_in_executor(
                    None,
                    lambda: WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".index_con_g22OA, .index_list_0FTJJ, .index_list_JdjrF"))
                    )
                )
                logger.info("快讯容器已加载")
            except Exception as e:
                logger.warning(f"等待快讯容器加载超时: {str(e)}")
            
            # 保存调试信息
            await self.save_debug_info(driver, "loaded")
            
            # 获取所有快讯项
            logger.info("开始提取快讯数据")
            
            # 尝试找到快讯容器
            news_container = None
            try:
                # 尝试查找快讯容器
                news_container = await loop.run_in_executor(
                    None,
                    lambda: driver.find_element(By.CSS_SELECTOR, ".index_con_g22OA, .index_list_0FTJJ, .index_list_JdjrF")
                )
                logger.info("找到快讯容器")
            except NoSuchElementException:
                logger.warning("未找到快讯容器")
            
            if news_container:
                # 获取日期标题
                date_headers = await loop.run_in_executor(
                    None,
                    lambda: news_container.find_elements(By.CSS_SELECTOR, ".index_timeTit_sZHis, .date-title")
                )
                
                date_group = ""
                if date_headers:
                    date_text = await loop.run_in_executor(
                        None,
                        lambda: date_headers[0].text.strip()
                    )
                    date_group = date_text
                    logger.info(f"找到日期分组: {date_group}")
                
                # 获取所有快讯项
                news_items_elements = await loop.run_in_executor(
                    None,
                    lambda: news_container.find_elements(By.CSS_SELECTOR, "li.clearfix, .news-item")
                )
                
                logger.info(f"找到 {len(news_items_elements)} 条快讯")
                
                # 处理每一条快讯
                for index, item in enumerate(news_items_elements):
                    try:
                        # 提取时间
                        time_element = await loop.run_in_executor(
                            None,
                            lambda: item.find_elements(By.CSS_SELECTOR, ".index_time_gw4oL, .time")
                        )
                        
                        time_text = ""
                        if time_element:
                            time_text = await loop.run_in_executor(
                                None,
                                lambda: time_element[0].text.strip()
                            )
                        
                        # 提取内容
                        content_element = await loop.run_in_executor(
                            None,
                            lambda: item.find_elements(By.CSS_SELECTOR, ".index_title_gFfxc, .content")
                        )
                        
                        content_text = ""
                        if content_element:
                            content_text = await loop.run_in_executor(
                                None,
                                lambda: content_element[0].text.strip()
                            )
                        
                        if not content_text:
                            logger.warning(f"快讯 {index} 没有内容，跳过")
                            continue
                        
                        # 简单处理内容，提取出更合适的标题
                        title_text = ""
                        if "<br>" in content_text:
                            # 如果内容包含换行，第一行作为标题，其余作为内容
                            title_parts = content_text.split('\n', 1)
                            title_text = title_parts[0].strip()
                            content = content_text if len(title_parts) <= 1 else title_parts[1].strip()
                        else:
                            # 截取前30个字符作为标题
                            title_text = content_text[:30] + ("..." if len(content_text) > 30 else "")
                            content = content_text
                        
                        # 解析时间
                        published_at = None
                        if time_text:
                            published_at = self.extract_date(time_text)
                            
                            # 如果有日期分组，结合日期和时间
                            if date_group and published_at:
                                # 尝试从日期分组提取日期
                                date_match = re.search(r'(\d{4})[\s年\.]+(\d{1,2})[\s月\.]+(\d{1,2})[日\s]*', date_group)
                                if date_match:
                                    year, month, day = map(int, date_match.groups())
                                    published_at = datetime.datetime.combine(
                                        datetime.date(year, month, day),
                                        published_at.time()
                                    )
                        
                        if not published_at:
                            published_at = datetime.datetime.now()
                        
                        # 生成唯一ID
                        item_id = self.generate_id(self.url, f"{time_text}-{content_text[:50]}")
                        
                        # 创建新闻项
                        news_item = NewsItemModel(
                            id=item_id,
                            title=title_text,
                            url=self.url,  # 由于快报项没有单独的URL，使用页面URL
                            source_id=self.source_id,
                            source_name=self.name,
                            content=content,
                            summary=content[:200] + ("..." if len(content) > 200 else ""),
                            published_at=published_at,
                            language=self.language,
                            country=self.country,
                            category=self.category,
                            extra={
                                "time_text": time_text,
                                "date_group": date_group,
                                "type": "快报",
                                "platform": "凤凰财经",
                                "source_from": "selenium",
                                "rank": index + 1
                            }
                        )
                        
                        news_items.append(news_item)
                        
                    except Exception as e:
                        logger.error(f"处理快讯 {index} 失败: {str(e)}")
            
            # 如果无法通过Selenium提取，尝试从页面源码提取
            if not news_items:
                logger.warning("通过Selenium未提取到快讯，尝试从页面源码提取")
                
                # 获取页面源码
                page_source = await loop.run_in_executor(None, lambda: driver.page_source)
                
                # 使用BeautifulSoup解析
                try:
                    items = await self.parse_response(page_source)
                    if items:
                        logger.info(f"通过BeautifulSoup提取到 {len(items)} 条快讯")
                        news_items = items
                except Exception as bs_e:
                    logger.error(f"使用BeautifulSoup解析失败: {str(bs_e)}")
            
            # 按时间排序
            news_items.sort(
                key=lambda x: x.published_at,
                reverse=True  # 最新的排在前面
            )
            
            logger.info(f"成功获取 {len(news_items)} 条凤凰财经快讯")
            return news_items
            
        except Exception as e:
            logger.error(f"获取凤凰财经快讯失败: {str(e)}")
            await self.save_debug_info(driver, "error")
            return []
        finally:
            await self._close_driver()
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析凤凰财经全球快报页面 - HTTP备用方法
        
        Args:
            response: 网页响应内容
            
        Returns:
            解析后的新闻项列表
        """
        logger.info("开始解析凤凰财经全球快报页面")
        news_items = []
        
        try:
            soup = BeautifulSoup(response, 'html.parser')
            
            # 根据提供的HTML结构，查找新闻列表
            news_list = soup.select(".index_list_0FTJJ ul li.clearfix, .index_list_JdjrF ul li.clearfix")
            
            if not news_list:
                logger.warning("未找到凤凰财经全球快报列表或列表为空")
                # 尝试其他选择器
                news_list = soup.select(".news-list .news-item, .flash-items .flash-item")
                
                if not news_list:
                    logger.warning("使用备用选择器也未找到快讯列表")
                    return []
            
            logger.info(f"找到 {len(news_list)} 条快报信息")
            
            # 查找日期标题
            date_headers = soup.select(".index_timeTit_sZHis, .date-title")
            date_group = ""
            if date_headers:
                date_group = date_headers[0].text.strip()
                logger.info(f"找到日期分组: {date_group}")
            
            for index, item in enumerate(news_list):
                try:
                    # 提取时间
                    time_element = item.select_one(".index_time_gw4oL, .time")
                    time_text = time_element.text.strip() if time_element else ""
                    
                    # 提取标题和内容
                    title_element = item.select_one(".index_title_gFfxc, .content")
                    if not title_element:
                        continue
                        
                    content_text = title_element.text.strip()
                    
                    # 简单处理一下，提取出更合适的标题
                    # 如果内容包含换行，第一行作为标题，其余作为内容
                    if "<br>" in str(title_element):
                        title_parts = content_text.split('\n', 1)
                        title_text = title_parts[0].strip()
                        content = content_text if len(title_parts) <= 1 else title_parts[1].strip()
                    else:
                        # 截取前30个字符作为标题
                        title_text = content_text[:30] + ("..." if len(content_text) > 30 else "")
                        content = content_text
                    
                    # 生成唯一ID
                    item_id = hashlib.md5(f"ifeng-studio-{time_text}-{content_text[:100]}".encode()).hexdigest()
                    
                    # 解析时间
                    published_at = None
                    if time_text:
                        published_at = self.extract_date(time_text)
                        
                        # 如果有日期分组，结合日期和时间
                        if date_group and published_at:
                            # 尝试从日期分组提取日期
                            date_match = re.search(r'(\d{4})[\s年\.]+(\d{1,2})[\s月\.]+(\d{1,2})[日\s]*', date_group)
                            if date_match:
                                year, month, day = map(int, date_match.groups())
                                published_at = datetime.datetime.combine(
                                    datetime.date(year, month, day),
                                    published_at.time()
                                )
                    
                    if not published_at:
                        published_at = datetime.datetime.now()
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=item_id,
                        title=title_text,
                        url=self.url,  # 由于快报项没有单独的URL，使用页面URL
                        source_id=self.source_id,
                        source_name=self.name,
                        content=content,
                        summary=content[:200] + ("..." if len(content) > 200 else ""),
                        published_at=published_at,
                        language=self.language,
                        country=self.country,
                        category=self.category,
                        extra={
                            "time_text": time_text,
                            "date_group": date_group,
                            "type": "快报",
                            "platform": "凤凰财经",
                            "source_from": "http_fallback",
                            "rank": index + 1
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"解析凤凰财经快报项时出错: {str(e)}")
            
            # 按发布时间降序排序
            news_items.sort(key=lambda x: x.published_at, reverse=True)
            
            logger.info(f"成功解析 {len(news_items)} 条凤凰财经快报")
            return news_items
            
        except Exception as e:
            logger.error(f"解析凤凰财经全球快报页面出错: {str(e)}")
            return []


class IfengTechSource(IfengBaseSource):
    """
    凤凰科技新闻适配器
    获取凤凰科技频道最新新闻
    使用Selenium获取页面源码，然后通过BeautifulSoup解析内容
    """
    
    def __init__(
        self,
        source_id: str = "ifeng-tech",
        name: str = "凤凰科技",
        url: str = "https://tech.ifeng.com/",
        update_interval: int = 1800,  # 30分钟更新一次
        cache_ttl: int = 1200,  # 20分钟缓存有效期，延长TTL提高缓存命中率
        category: str = "technology",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        # 配置特定设置
        config = config or {}
        config.update({
            # 设置合理的超时时间
            "selenium_timeout": 5,  # 适当减少超时时间
            # 调试配置
            "save_debug_info": DEBUG_MODE,
            # HTTP备用
            "use_http_fallback": True,
            # 强制启用缓存
            "use_cache": True,
            # 指定最大获取条目数
            "max_items": 30,
        })
        
        # 强制统一source_id
        if source_id != "ifeng-tech":
            logger.warning(f"源ID '{source_id}' 被统一为标准ID 'ifeng-tech'")
            source_id = "ifeng-tech"
            
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
        """
        使用Selenium获取凤凰科技新闻页面，然后通过BeautifulSoup解析内容
        由于WebElement处理存在问题，我们直接获取页面源码后用BeautifulSoup解析
        """
        logger.info("开始获取凤凰科技新闻")
        driver = await self._get_driver()
        if driver is None:
            logger.error("WebDriver创建失败")
            return []
        
        news_items = []
        
        try:
            # 访问科技新闻页面
            logger.info(f"访问科技新闻URL: {self.url}")
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
            scroll_script = """
            function smoothScroll() {
                return new Promise((resolve) => {
                    let totalHeight = 0;
                    let distance = 300;
                    let timer = setInterval(() => {
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        
                        // 减少滚动距离，只滚动到足够看到主要内容的位置
                        if(totalHeight >= 3000) {  // 从10000减少到3000
                            clearInterval(timer);
                            resolve("滚动完成");
                        }
                    }, 200);
                });
            }
            return smoothScroll();
            """
            try:
                scroll_result = await loop.run_in_executor(
                    None, 
                    lambda: driver.execute_script(scroll_script)
                )
                logger.info(f"滚动结果: {scroll_result}")
            except:
                logger.warning("执行滚动脚本失败")
            
            # 等待动态内容加载
            await asyncio.sleep(1)
            
            # 保存调试信息
            await self.save_debug_info(driver, "scrolled")
            
            # 获取页面源码，跳过有问题的WebElement处理
            page_source = await loop.run_in_executor(None, lambda: driver.page_source)
            
            # 使用BeautifulSoup解析
            try:
                news_items = await self.parse_response(page_source)
                logger.info(f"成功解析出 {len(news_items)} 条科技新闻")
            except Exception as bs_e:
                logger.error(f"解析页面内容失败: {str(bs_e)}")
            
            logger.info(f"成功获取 {len(news_items)} 条凤凰科技新闻")
            return news_items
            
        except Exception as e:
            logger.error(f"获取凤凰科技新闻失败: {str(e)}")
            await self.save_debug_info(driver, "error")
            return []
        finally:
            await self._close_driver()
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        解析凤凰科技新闻页面
        
        Args:
            response: 网页响应内容
            
        Returns:
            解析后的新闻项列表
        """
        logger.info("开始解析凤凰科技新闻页面")
        news_items = []
        max_items = self.config.get("max_items", 30)
        
        try:
            soup = BeautifulSoup(response, 'html.parser')
            
            # 尝试不同的新闻列表选择器 - 更新为当前网页结构
            news_list = []
            
            # 按照提供的HTML结构添加新的选择器
            selectors = [
                ".style_left_WIE3r .index_news_item_U0V7S",  # 左侧列表中的新闻项
                ".style_left_WIE3r .index_news_top_item_At6jN",  # 左侧列表中的置顶新闻项
            ]
            
            for selector in selectors:
                items = soup.select(selector)
                if items:
                    logger.info(f"使用选择器 {selector} 找到 {len(items)} 条新闻")
                    news_list.extend(items)  # 使用extend合并多个选择器的结果
            
            # 去重处理
            if news_list:
                # 使用URL作为唯一标识进行去重
                unique_urls = set()
                unique_news_list = []
                
                for item in news_list:
                    # 查找链接和标题
                    if item.name == "a" and "/c/" in item.get("href", ""):
                        item_url = item.get("href", "")
                        if item_url and item_url not in unique_urls:
                            unique_urls.add(item_url)
                            unique_news_list.append(item)
                    else:
                        # 查找链接元素
                        link_element = item.select_one(".index_title_oqpqT") or item.select_one("a[href*='/c/']")
                        if link_element:
                            item_url = link_element.get("href", "")
                            if item_url and item_url not in unique_urls:
                                unique_urls.add(item_url)
                                unique_news_list.append(item)
                
                news_list = unique_news_list
                logger.info(f"去重后剩余 {len(news_list)} 条唯一新闻")
            
            if not news_list:
                logger.warning("未找到凤凰科技新闻列表或列表为空")
                return []
            
            # 限制处理的新闻条数
            if len(news_list) > max_items:
                news_list = news_list[:max_items]
            
            for index, item in enumerate(news_list):
                try:
                    # 提取链接和标题 - 更新为当前网页结构
                    item_url = ""
                    title = ""
                    time_text = ""
                    
                    # 如果元素本身是链接
                    if item.name == "a" and "/c/" in item.get("href", ""):
                        item_url = item.get("href", "")
                        title = item.get_text(strip=True)
                    else:
                        # 查找标题和链接元素
                        title_element = item.select_one(".index_title_oqpqT") or item.select_one("a[href*='/c/']")
                        if title_element:
                            item_url = title_element.get("href", "")
                            title = title_element.get_text(strip=True)
                            
                            # 检查title属性可能包含完整标题
                            title_attr = title_element.get("title")
                            if title_attr and len(title_attr) > len(title):
                                title = title_attr
                    
                    # 如果没有URL，跳过
                    if not item_url:
                        continue
                    
                    # 确保链接是绝对路径
                    if not item_url.startswith("http"):
                        if item_url.startswith("/"):
                            item_url = "https://tech.ifeng.com" + item_url
                        else:
                            item_url = "https://tech.ifeng.com/" + item_url
                    
                    # 提取时间 - 更新为当前网页结构
                    time_element = item.select_one(".index_date_sP1mT") or item.select_one(".time, .date, .news-date")
                    
                    published_at = None
                    if time_element:
                        time_text = time_element.get_text(strip=True)
                        
                        # 查找title属性，可能包含完整日期时间
                        time_title = time_element.get("title")
                        if time_title and re.match(r'\d{4}-\d{2}-\d{2}', time_title):
                            logger.info(f"使用title属性中的完整时间: {time_title}")
                            published_at = self.extract_date(time_title)
                        elif time_text:
                            published_at = self.extract_date(time_text)
                    
                    # 如果没有时间，使用当前时间
                    if not published_at:
                        published_at = datetime.datetime.now()
                    
                    # 生成唯一ID
                    item_id = self.generate_id(item_url, title)
                    
                    # 创建新闻项
                    news_item = NewsItemModel(
                        id=item_id,
                        title=title,
                        url=item_url,
                        source_id=self.source_id,
                        source_name=self.name,
                        content="",  # 暂时空，需要访问具体页面获取
                        summary=title,  # 使用标题作为摘要
                        published_at=published_at,
                        language=self.language,
                        country=self.country,
                        category=self.category,
                        extra={
                            "time_text": time_text,
                            "type": "科技新闻",
                            "platform": "凤凰科技",
                            "source_from": "selenium+beautifulsoup",
                            "rank": index + 1
                        }
                    )
                    
                    news_items.append(news_item)
                
                except Exception as e:
                    logger.error(f"解析科技新闻项 {index} 失败: {str(e)}")
            
            # 按发布时间排序
            news_items.sort(key=lambda x: x.published_at, reverse=True)
            
            logger.info(f"成功解析 {len(news_items)} 条凤凰科技新闻")
            return news_items
            
        except Exception as e:
            logger.error(f"解析凤凰科技新闻页面失败: {str(e)}")
            return []


def create_source(source_id: str, config: Optional[Dict[str, Any]] = None) -> Optional[IfengBaseSource]:
    """
    根据source_id创建对应的凤凰新闻源
    
    Args:
        source_id: 源标识符
        config: 可选配置
        
    Returns:
        对应的凤凰新闻源实例，如果source_id不匹配则返回None
    """
    logger.info(f"创建凤凰新闻源: {source_id}")
    
    if source_id == "ifeng-studio":
        return IfengStudioSource(config=config)
    elif source_id == "ifeng-tech":
        return IfengTechSource(config=config)
    else:
        logger.warning(f"未知的凤凰新闻源ID: {source_id}")
        return None

# 导出类和工厂函数
__all__ = [
    "IfengBaseSource",
    "IfengStudioSource",
    "IfengTechSource",
    "create_source"
]

# 如果作为主模块运行，测试源
if __name__ == "__main__":
    import asyncio
    import json
    
    async def test_source(source_id: str):
        # 开启调试模式
        global DEBUG_MODE
        DEBUG_MODE = True
        
        # 创建源
        source = create_source(source_id)
        if not source:
            print(f"创建源 {source_id} 失败")
            return
        
        print(f"开始测试源: {source.name} (ID: {source.source_id})")
        
        # 获取数据
        try:
            news_items = await source.fetch()
            print(f"获取到 {len(news_items)} 条新闻")
            
            # 打印前5条新闻
            for i, item in enumerate(news_items[:5]):
                print(f"== 新闻 {i+1} ==")
                print(f"ID: {item.id}")
                print(f"标题: {item.title}")
                print(f"URL: {item.url}")
                print(f"发布时间: {item.published_at}")
                print(f"摘要: {item.summary[:100]}...")
                print(f"额外信息: {json.dumps(item.extra, ensure_ascii=False)}")
                print()
            
        except Exception as e:
            print(f"测试源时出错: {str(e)}")
        finally:
            # 关闭源
            await source.close()
    
    # 测试所有源
    async def main():
        for source_id in ["ifeng-studio", "ifeng-tech"]:
            await test_source(source_id)
            print("\n" + "="*50 + "\n")
    
    # 运行测试
    asyncio.run(main()) 