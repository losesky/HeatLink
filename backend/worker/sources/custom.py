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
from urllib.parse import urljoin, urlparse

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
        self._chrome_user_data_dir = None
        
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
            
            # 首先尝试使用psutil清理残留的Chrome进程
            try:
                import psutil
                import signal
                
                chrome_process_count = 0
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        # 查找Chrome或ChromeDriver进程
                        pname = proc.info['name']
                        if pname and ('chrome' in pname.lower() or 'chromedriver' in pname.lower()):
                            try:
                                proc.terminate()  # 优雅地终止
                                chrome_process_count += 1
                            except:
                                try:
                                    proc.kill()  # 如果优雅终止失败，强制终止
                                    chrome_process_count += 1
                                except:
                                    pass
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
                
                if chrome_process_count > 0:
                    logger.info(f"在创建WebDriver前终止了 {chrome_process_count} 个Chrome相关进程")
                    
                    # 等待进程完全退出
                    time.sleep(0.5)
            except Exception as e:
                logger.warning(f"清理Chrome进程时出错: {str(e)}")
            
            # 清理旧的Chrome用户数据目录
            try:
                import glob
                import shutil
                
                # 查找/tmp目录下的所有Chrome用户数据目录
                chrome_dirs = glob.glob("/tmp/chrome_data_dir_*")
                removed_count = 0
                
                for dir_path in chrome_dirs:
                    try:
                        if os.path.isdir(dir_path):
                            shutil.rmtree(dir_path, ignore_errors=True)
                            removed_count += 1
                    except Exception:
                        pass
                
                if removed_count > 0:
                    logger.info(f"清理了 {removed_count} 个旧的Chrome用户数据目录")
            except Exception as clean_e:
                logger.warning(f"清理旧的Chrome用户数据目录时出错: {str(clean_e)}")
            
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
            
            # 设置唯一的远程调试端口，避免端口冲突
            unique_port = random.randint(9000, 9999)
            chrome_options.add_argument(f"--remote-debugging-port={unique_port}")
            logger.debug(f"设置唯一远程调试端口: {unique_port}")
            
            # 存储用户数据目录路径以便后续清理
            self._chrome_user_data_dir = unique_dir
            
            # 强制禁用GPU
            chrome_options.add_argument("--disable-gpu")
            
            # 禁用扩展
            chrome_options.add_argument("--disable-extensions")
            
            # 禁用开发者工具
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            # 禁用沙盒
            chrome_options.add_argument("--no-sandbox")
            
            # 禁用自动化控制提示
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            
            # 启用JavaScript
            chrome_options.add_argument("--enable-javascript")
            
            # 设置语言
            chrome_options.add_argument(f"--lang={self.language}")
            
            # 检测WSL环境 - 使用统一的配置
            if "microsoft" in platform.uname().release.lower() or os.name == 'nt':
                logger.info("检测到WSL/Windows环境，应用特殊配置")
                # WSL必须的参数
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
            
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
                    
                # 清理用户数据目录
                if hasattr(self, '_chrome_user_data_dir') and self._chrome_user_data_dir:
                    try:
                        import shutil
                        if os.path.exists(self._chrome_user_data_dir):
                            shutil.rmtree(self._chrome_user_data_dir, ignore_errors=True)
                            logger.debug(f"已清理用户数据目录: {self._chrome_user_data_dir}")
                    except Exception as rm_e:
                        logger.warning(f"清理用户数据目录失败: {str(rm_e)}")
                    self._chrome_user_data_dir = None
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
        
    async def clean_chrome_processes(self):
        """
        清理可能导致"user data directory is already in use"错误的Chrome进程
        """
        try:
            import psutil
            chrome_count = 0
            chromedriver_count = 0
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # 检查是否为Chrome相关进程
                    proc_name = proc.info['name'] if proc.info['name'] else ""
                    proc_cmdline = proc.info['cmdline'] if proc.info['cmdline'] else []
                    
                    # 转换为字符串进行检查
                    cmdline_str = ' '.join(proc_cmdline).lower() if proc_cmdline else ""
                    
                    # 识别Chrome浏览器进程
                    is_chrome = ("chrome" in proc_name.lower() or "chromium" in proc_name.lower()) and "chromedriver" not in proc_name.lower()
                    
                    # 识别ChromeDriver进程
                    is_chromedriver = "chromedriver" in proc_name.lower()
                    
                    # 检查是否是我们之前启动的，使用相同的用户数据目录
                    if hasattr(self, '_chrome_user_data_dir') and self._chrome_user_data_dir:
                        is_our_chrome = self._chrome_user_data_dir in cmdline_str
                    else:
                        is_our_chrome = False
                    
                    # 处理Chrome浏览器进程
                    if is_chrome and is_our_chrome:
                        try:
                            proc.terminate()
                            logger.info(f"终止Chrome进程 (PID: {proc.pid})")
                            chrome_count += 1
                        except:
                            try:
                                proc.kill()
                                logger.info(f"强制终止Chrome进程 (PID: {proc.pid})")
                                chrome_count += 1
                            except Exception as e:
                                logger.warning(f"无法终止Chrome进程 (PID: {proc.pid}): {str(e)}")
                    
                    # 处理ChromeDriver进程
                    if is_chromedriver:
                        try:
                            proc.terminate()
                            logger.info(f"终止ChromeDriver进程 (PID: {proc.pid})")
                            chromedriver_count += 1
                        except:
                            try:
                                proc.kill()
                                logger.info(f"强制终止ChromeDriver进程 (PID: {proc.pid})")
                                chromedriver_count += 1
                            except Exception as e:
                                logger.warning(f"无法终止ChromeDriver进程 (PID: {proc.pid}): {str(e)}")
                
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
                except Exception as e:
                    logger.warning(f"检查进程时出错: {str(e)}")
            
            if chrome_count > 0 or chromedriver_count > 0:
                logger.info(f"清理了 {chrome_count} 个Chrome进程和 {chromedriver_count} 个ChromeDriver进程")
            
            # 确保用户数据目录被清理
            if hasattr(self, '_chrome_user_data_dir') and self._chrome_user_data_dir and os.path.exists(self._chrome_user_data_dir):
                try:
                    import shutil
                    shutil.rmtree(self._chrome_user_data_dir, ignore_errors=True)
                    logger.info(f"清理用户数据目录: {self._chrome_user_data_dir}")
                    self._chrome_user_data_dir = None
                except Exception as e:
                    logger.warning(f"清理用户数据目录失败: {str(e)}")
        
        except Exception as e:
            logger.error(f"清理Chrome进程时出错: {str(e)}")

    async def fetch(self) -> List[NewsItemModel]:
        """
        获取新闻数据
        
        Returns:
            List[NewsItemModel]: 新闻项目列表
        """
        start_time = time.time()
        
        try:
            # 清理可能存在的旧进程，避免"user data directory is already in use"错误
            await self.clean_chrome_processes()
            
            logger.info(f"开始获取 {self.name} 数据")
            
            # 检查是否使用缓存及是否有缓存
            if self.config.get("use_cache", True):
                # 尝试获取缓存
                cached_news = await self.get_cached_news()
                if cached_news:
                    logger.info(f"使用缓存的 {self.name} 数据，共 {len(cached_news)} 条")
                    return cached_news
            
            # 实际获取新闻的实现
            news_items = await self._fetch_impl()
            
            # 记录获取成功及耗时
            elapsed = time.time() - start_time
            logger.info(f"成功获取 {len(news_items)} 条 {self.name} 数据，耗时 {elapsed:.2f} 秒")
            
            # 更新缓存
            if self.config.get("use_cache", True) and news_items:
                await self.update_cache(news_items)
            
            return news_items
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"获取 {self.name} 数据失败: {str(e)}，耗时 {elapsed:.2f} 秒")
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
                        # 特殊处理：首先检测是否为NBD网站结构
                        is_nbd_structure = False
                        
                        # 检查是否存在NBD特有的元素
                        try:
                            # 先检查更具体的NBD结构标志
                            nbd_specific_elements = await loop.run_in_executor(
                                None,
                                lambda: item.find_elements(By.CSS_SELECTOR, '.u-newsText .u-content, .u-time')
                            )
                            
                            if nbd_specific_elements and len(nbd_specific_elements) > 0:
                                is_nbd_structure = True
                                logger.info(f"项目 {index} 检测到NBD网站结构")
                            else:
                                # 再检查父元素结构是否为NBD网站的kuaiXunBox
                                parent_check = await loop.run_in_executor(
                                    None,
                                    lambda: driver.execute_script("""
                                        function checkNBDParent(element) {
                                            let parent = element.parentElement;
                                            while (parent) {
                                                if (parent.classList.contains('kuaiXunBox')) return true;
                                                parent = parent.parentElement;
                                            }
                                            return false;
                                        }
                                        return checkNBDParent(arguments[0]);
                                    """, item)
                                )
                                
                                if parent_check:
                                    is_nbd_structure = True
                                    logger.info(f"项目 {index} 通过父元素检测确认为NBD网站结构")
                        except Exception as e:
                            logger.debug(f"检测NBD结构时出错: {str(e)}")
                        
                        # 通用智能结构检测 - 根据常见模式自动识别新闻项结构特征
                        if not is_nbd_structure:
                            try:
                                # 检查通用新闻项特征
                                structure_info = await loop.run_in_executor(
                                    None,
                                    lambda: driver.execute_script("""
                                        function detectNewsStructure(element) {
                                            const result = {
                                                hasTitle: false,
                                                titleElement: null,
                                                titleSelector: '',
                                                hasTime: false,
                                                timeElement: null,
                                                timeSelector: '',
                                                hasLink: false,
                                                linkElement: null,
                                                linkSelector: '',
                                                hasContent: false,
                                                contentElement: null,
                                                contentSelector: ''
                                            };
                                            
                                            // 检查标题类元素 (h1-h5, strong, b, 或特定类)
                                            const titleElements = element.querySelectorAll('h1, h2, h3, h4, h5, strong, b, [class*="title"], [class*="heading"]');
                                            if (titleElements.length > 0) {
                                                result.hasTitle = true;
                                                result.titleElement = titleElements[0];
                                                result.titleSelector = titleElements[0].tagName.toLowerCase();
                                                if (titleElements[0].className) {
                                                    result.titleSelector += '.' + titleElements[0].className.split(' ').join('.');
                                                }
                                            }
                                            
                                            // 检查时间类元素 (time, span或div包含时间格式)
                                            const timeElements = Array.from(element.querySelectorAll('time, span, div, [class*="time"], [class*="date"]'))
                                                .filter(el => {
                                                    const text = el.textContent.trim();
                                                    return /\\d{1,2}:\\d{1,2}/.test(text) || // 12:34
                                                           /\\d{4}[-\\/]\\d{1,2}[-\\/]\\d{1,2}/.test(text) || // 2025-01-01
                                                           /(分钟前|小时前|天前|周前|月前|年前)/.test(text); // 相对时间
                                                });
                                            
                                            if (timeElements.length > 0) {
                                                result.hasTime = true;
                                                result.timeElement = timeElements[0];
                                                result.timeSelector = timeElements[0].tagName.toLowerCase();
                                                if (timeElements[0].className) {
                                                    result.timeSelector += '.' + timeElements[0].className.split(' ').join('.');
                                                }
                                            }
                                            
                                            // 检查链接元素 (a标签)
                                            const linkElements = element.querySelectorAll('a[href]');
                                            if (linkElements.length > 0) {
                                                result.hasLink = true;
                                                result.linkElement = linkElements[0];
                                                result.linkSelector = 'a';
                                            }
                                            
                                            // 检查内容/摘要类元素 (p, div包含较长文本)
                                            const contentElements = Array.from(element.querySelectorAll('p, div, [class*="content"], [class*="summary"], [class*="desc"]'))
                                                .filter(el => {
                                                    const text = el.textContent.trim();
                                                    return text.length > 20 && text.split(' ').length > 3;
                                                });
                                                
                                            if (contentElements.length > 0) {
                                                result.hasContent = true;
                                                result.contentElement = contentElements[0];
                                                result.contentSelector = contentElements[0].tagName.toLowerCase();
                                                if (contentElements[0].className) {
                                                    result.contentSelector += '.' + contentElements[0].className.split(' ').join('.');
                                                }
                                            }
                                            
                                            return result;
                                        }
                                        return detectNewsStructure(arguments[0]);
                                    """, item)
                                )
                                
                                # 基于结构信息判断是否为新闻项
                                if structure_info and (structure_info.get('hasTitle') or structure_info.get('hasContent')):
                                    logger.info(f"项目 {index} 通过智能结构分析识别为新闻项")
                            except Exception as struct_e:
                                logger.debug(f"进行智能结构检测时出错: {str(struct_e)}")
                        
                        # 提取标题
                        title = ""
                        title_element = None  # 确保在所有代码路径中初始化title_element
                        
                        # 针对NBD特殊处理 - 首先尝试直接从结构获取
                        if is_nbd_structure:
                            try:
                                # 1. 首先尝试从title属性获取标题
                                try:
                                    title_from_attr = await loop.run_in_executor(
                                        None,
                                        lambda: item.get_attribute('title')
                                    )
                                    
                                    if not title_from_attr:
                                        # 检查a标签的title属性
                                        a_elements = await loop.run_in_executor(
                                            None,
                                            lambda: item.find_elements(By.CSS_SELECTOR, 'a')
                                        )
                                        
                                        for a_elem in a_elements:
                                            a_title = await loop.run_in_executor(
                                                None,
                                                lambda: a_elem.get_attribute('title')
                                            )
                                            if a_title and a_title.strip():
                                                title = a_title.strip()
                                                logger.info(f"从a标签title属性获取到标题: {title}")
                                                break
                                    else:
                                        title = title_from_attr
                                        logger.info(f"从元素title属性获取到标题: {title}")
                                except Exception as attr_e:
                                    logger.debug(f"从title属性获取标题失败: {str(attr_e)}")
                                
                                # 2. 尝试直接从.u-newsText .u-content元素获取
                                if not title:
                                    news_content_elements = await loop.run_in_executor(
                                        None,
                                        lambda: item.find_elements(By.CSS_SELECTOR, '.u-newsText .u-content')
                                    )
                                    
                                    if news_content_elements and len(news_content_elements) > 0:
                                        for content_elem in news_content_elements:
                                            content_text = await loop.run_in_executor(
                                                None,
                                                lambda: content_elem.text.strip()
                                            )
                                            if content_text:
                                                title = content_text
                                                logger.info(f"从.u-newsText .u-content获取到标题: {title}")
                                                break
                                
                                # 3. 使用JavaScript获取元素内容 - 直接从DOM获取text内容
                                if not title:
                                    try:
                                        js_content = await loop.run_in_executor(
                                            None,
                                            lambda: driver.execute_script("""
                                                function getNBDTitle(element) {
                                                    // 尝试获取.u-content内容
                                                    let contentElem = element.querySelector('.u-content');
                                                    if (contentElem && contentElem.textContent.trim()) {
                                                        return contentElem.textContent.trim();
                                                    }
                                                    
                                                    // 尝试获取a标签的文本内容（排除时间）
                                                    let aElem = element.querySelector('a');
                                                    if (aElem) {
                                                        let fullText = aElem.textContent.trim();
                                                        // 移除时间部分 (例如 "12:34")
                                                        let timeElem = aElem.querySelector('.u-time');
                                                        if (timeElem) {
                                                            let timeText = timeElem.textContent.trim();
                                                            fullText = fullText.replace(timeText, '').trim();
                                                        }
                                                        if (fullText) return fullText;
                                                    }
                                                    
                                                    // 尝试获取整个项目文本（排除时间）
                                                    let fullText = element.textContent.trim();
                                                    let timeElem = element.querySelector('.u-time');
                                                    if (timeElem) {
                                                        let timeText = timeElem.textContent.trim();
                                                        fullText = fullText.replace(timeText, '').trim();
                                                    }
                                                    return fullText;
                                                }
                                                return getNBDTitle(arguments[0]);
                                            """, item)
                                        )
                                        
                                        if js_content and js_content.strip():
                                            title = js_content.strip()
                                            logger.info(f"从JavaScript获取到标题: {title}")
                                    except Exception as js_e:
                                        logger.debug(f"使用JavaScript获取标题失败: {str(js_e)}")
                                
                                # 4. 如果上面失败，尝试从a标签直接获取内容
                                if not title:
                                    a_elements = await loop.run_in_executor(
                                        None,
                                        lambda: item.find_elements(By.CSS_SELECTOR, 'a')
                                    )
                                    
                                    for a_elem in a_elements:
                                        a_text = await loop.run_in_executor(
                                            None,
                                            lambda: a_elem.text.strip()
                                        )
                                        # 过滤掉只有时间的a标签
                                        if a_text and not re.match(r'^\d{1,2}:\d{1,2}$', a_text):
                                            # 尝试移除时间部分 (格式如 "标题 12:34")
                                            time_pattern = r'\d{1,2}:\d{1,2}'
                                            a_text = re.sub(time_pattern, '', a_text).strip()
                                            if a_text:
                                                title = a_text
                                                logger.info(f"从a标签获取到标题: {title}")
                                                break
                                
                                # 5. 使用通用智能提取方法
                                if not title:
                                    smart_title = await loop.run_in_executor(
                                        None,
                                        lambda: driver.execute_script("""
                                            function smartExtractTitle(element) {
                                                // 智能识别最可能是标题的文本内容
                                                
                                                // 1. 优先检查明确的标题元素
                                                const titleTags = ['h1', 'h2', 'h3', 'h4', 'h5'];
                                                for (const tag of titleTags) {
                                                    const elements = element.querySelectorAll(tag);
                                                    if (elements.length > 0) {
                                                        return elements[0].textContent.trim();
                                                    }
                                                }
                                                
                                                // 2. 检查类名包含标题相关的元素
                                                const titleClasses = Array.from(element.querySelectorAll('[class*="title"],[class*="heading"],[class*="caption"],[class*="subject"]'));
                                                if (titleClasses.length > 0) {
                                                    return titleClasses[0].textContent.trim();
                                                }
                                                
                                                // 3. 检查加粗文本
                                                const boldElements = element.querySelectorAll('strong, b');
                                                if (boldElements.length > 0) {
                                                    return boldElements[0].textContent.trim();
                                                }
                                                
                                                // 4. 尝试查找最短的非空文本块（通常是标题）
                                                const textElements = Array.from(element.querySelectorAll('*'))
                                                    .filter(el => {
                                                        const text = el.textContent.trim();
                                                        return text.length > 0 && 
                                                               text.length < 100 && 
                                                               !text.match(/^\\d{1,2}:\\d{1,2}$/) && // 排除时间
                                                               el.children.length === 0; // 只要叶子节点
                                                    });
                                                
                                                if (textElements.length > 0) {
                                                    // 按文本长度排序
                                                    textElements.sort((a, b) => a.textContent.trim().length - b.textContent.trim().length);
                                                    // 返回最短的非空文本块（可能是标题）
                                                    return textElements[0].textContent.trim();
                                                }
                                                
                                                // 5. 如果以上都失败，返回元素的完整文本（移除可能的时间）
                                                let fullText = element.textContent.trim();
                                                fullText = fullText.replace(/\\d{1,2}:\\d{1,2}/, '').trim();
                                                
                                                return fullText;
                                            }
                                            return smartExtractTitle(arguments[0]);
                                        """, item)
                                    )
                                    
                                    if smart_title and smart_title.strip():
                                        title = smart_title.strip()
                                        logger.info(f"使用智能标题提取获取到标题: {title}")
                            
                            except Exception as nbd_e:
                                logger.warning(f"NBD特殊处理提取标题时出错: {str(nbd_e)}")
                        
                        # 使用通用智能提取方法 - 适用于各种网站结构
                        if not title:
                            try:
                                # 通用智能提取标题
                                smart_title = await loop.run_in_executor(
                                    None,
                                    lambda: driver.execute_script("""
                                        function extractSmartTitle(element) {
                                            // 1. 优先从标题类元素中获取
                                            const titleElements = element.querySelectorAll('h1, h2, h3, h4, h5, [class*="title"], [class*="header"], [class*="heading"]');
                                            if (titleElements.length > 0) {
                                                return titleElements[0].textContent.trim();
                                            }
                                            
                                            // 2. 从链接获取 - 特别优化多链接场景
                                            const links = element.querySelectorAll('a[href]');
                                            if (links.length > 0) {
                                                // 如果有多个链接，查找文本内容最长的链接（通常是标题链接）
                                                let longestTextLink = null;
                                                let longestTextLength = 0;
                                                
                                                for (const link of links) {
                                                    const linkText = link.textContent.trim();
                                                    // 忽略明显不是标题的短链接，如分类标签和时间
                                                    if (linkText.length > longestTextLength && linkText.length > 5 && 
                                                        !linkText.match(/^\\[.*\\]$/) && // 排除[分类]格式
                                                        !linkText.match(/^\\d{1,2}:\\d{1,2}$/)) { // 排除时间格式
                                                        longestTextLength = linkText.length;
                                                        longestTextLink = link;
                                                    }
                                                }
                                                
                                                // 使用最长的链接文本作为标题
                                                if (longestTextLink) {
                                                    return longestTextLink.textContent.trim();
                                                }
                                                
                                                // 优先获取链接的title属性
                                                if (links[0].hasAttribute('title') && links[0].getAttribute('title').trim()) {
                                                    return links[0].getAttribute('title').trim();
                                                }
                                                
                                                // 获取链接文本，过滤掉时间
                                                let linkText = links[0].textContent.trim();
                                                // 移除时间类文本 (如 "12:34")
                                                linkText = linkText.replace(/\\d{1,2}:\\d{1,2}/, '').trim();
                                                if (linkText) return linkText;
                                            }
                                            
                                            // 3. 获取所有文本并移除时间部分
                                            let fullText = element.textContent.trim();
                                            
                                            // 移除常见的时间格式
                                            fullText = fullText.replace(/\\d{1,2}:\\d{1,2}/, ''); // 时:分
                                            fullText = fullText.replace(/\\d{4}[-\\/]\\d{1,2}[-\\/]\\d{1,2}/, ''); // 年-月-日
                                            
                                            return fullText.trim();
                                        }
                                        return extractSmartTitle(arguments[0]);
                                    """, item)
                                )
                                
                                if smart_title and smart_title.strip():
                                    title = smart_title.strip()
                                    logger.info(f"通用智能提取获取到标题: {title}")
                            except Exception as smart_e:
                                logger.warning(f"通用智能提取标题时出错: {str(smart_e)}")
                        
                        # 标准标题元素提取方法
                        if not title and title_selector:
                            try:
                                # 查找标题元素
                                title_element = await loop.run_in_executor(
                                    None,
                                    lambda: item.find_element(By.CSS_SELECTOR, title_selector)
                                )
                        
                                # 获取标题文本
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
                            
                                # 如果依然为空，尝试从父元素获取标题（通常是 a 标签）
                                if not title:
                                    try:
                                        # 初始化parent_link为None
                                        parent_link = None
                                        
                                        # 尝试找到包含当前元素的链接
                                        parent_link = await loop.run_in_executor(
                                            None,
                                            lambda: driver.execute_script("""
                                                function getParentLink(element) {
                                                    if (element.tagName === 'A') return element;
                                                    let parent = element.parentElement;
                                                    while (parent) {
                                                        if (parent.tagName === 'A') return parent;
                                                        parent = parent.parentElement;
                                                    }
                                                    return null;
                                                }
                                                return getParentLink(arguments[0]);
                                            """, title_element)
                                        )
                                        
                                        if parent_link:
                                            # 尝试从父链接获取title属性
                                            title = await loop.run_in_executor(
                                                None,
                                                lambda: parent_link.get_attribute('title')
                                            )
                                            
                                            # 如果父链接没有title属性，尝试获取其文本内容
                                            if not title:
                                                parent_text = await loop.run_in_executor(
                                                    None,
                                                    lambda: parent_link.text.strip()
                                                )
                                                
                                                # 过滤掉可能包含的时间文本，常见于NBD网站格式
                                                if parent_text:
                                                    # 尝试找到并移除时间文本
                                                    try:
                                                        time_element = await loop.run_in_executor(
                                                            None,
                                                            lambda: parent_link.find_element(By.CSS_SELECTOR, '.u-time')
                                                        )
                                                        time_text = await loop.run_in_executor(
                                                            None,
                                                            lambda: time_element.text.strip()
                                                        )
                                                        # 从父文本中移除时间文本
                                                        title = parent_text.replace(time_text, '').strip()
                                                    except NoSuchElementException:
                                                        # 如果没有找到时间元素，直接使用父文本
                                                        title = parent_text
                                    except Exception as parent_e:
                                        logger.warning(f"尝试从父元素获取标题时出错: {str(parent_e)}")
                            except NoSuchElementException:
                                logger.warning(f"项目 {index} 中未找到标题元素: {title_selector}")
                                continue
                            except Exception as e:
                                logger.warning(f"提取标题时出错: {str(e)}")
                        
                        # 如果使用所有方法后仍然为空，记录警告但不跳过此项
                        if not title:
                            title = f"未知标题 #{index+1}"
                            logger.warning(f"项目 {index} 的标题为空，使用默认标题: {title}")
                            # 额外调试日志，输出项目HTML以帮助排查
                            try:
                                item_html = await loop.run_in_executor(
                                    None,
                                    lambda: item.get_attribute('outerHTML')
                                )
                                logger.debug(f"项目 {index} HTML: {item_html[:500]}...")
                            except Exception as html_e:
                                logger.debug(f"获取项目HTML时出错: {str(html_e)}")
                        
                        # 提取链接
                        link = ""
                        # 如果在标题提取时已经找到链接，这里就不需要再提取了
                        if 'link' not in locals() or not link:
                            if link_selector:
                                link_elements = item.select(link_selector)
                                if link_elements:
                                    link = link_elements[0].get('href', '')
                            
                            # 如果找不到链接元素，尝试使用标题元素的href属性（如果title_element存在）
                            if not link and title_element is not None:
                                if title_element.name == 'a':
                                    link = title_element.get('href', '')
                                else:
                                    # 查找包含标题元素的链接
                                    parent_link = title_element.find_parent('a')
                                    if parent_link:
                                        link = parent_link.get('href', '')
                            
                            if link:
                                logger.info(f"项目 {index} 使用标题元素的href属性作为链接")
                        
                            # 如果仍然没有找到链接，尝试从所有链接中找到文本最长的链接
                            if not link and a_elements:
                                if len(a_elements) == 1:
                                    link = a_elements[0].get('href', '')
                                else:
                                    # 找出最可能是标题链接的那个（通常是文本最长的）
                                    longest_text = ""
                                    longest_link = ""
                                    
                                    for a_elem in a_elements:
                                        a_text = a_elem.get_text(strip=True)
                                        a_href = a_elem.get('href', '')
                                        
                                        # 排除分类链接、时间链接和其他明显不是标题的链接
                                        if (len(a_text) > len(longest_text) and 
                                            len(a_text) > 5 and 
                                            not re.match(r'^\[.*\]$', a_text) and 
                                            not re.match(r'^\d{1,2}:\d{1,2}$', a_text)):
                                            longest_text = a_text
                                            longest_link = a_href
                                    
                                    if longest_link:
                                        link = longest_link
                                        logger.info(f"项目 {index} 从最长链接文本获取到链接: {link}")
                                    else:
                                        link = a_elements[0].get('href', '')
                        
                        # 如果仍然没有找到链接，则使用主URL
                        if not link:
                            link = self.url
                            logger.warning(f"项目 {index} 没有链接，使用源URL: {self.url}")
                        
                        # 提取发布日期
                        published_at = datetime.datetime.now()
                        if date_selector:
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
                        
                        # 提取摘要
                        summary = ""
                        if summary_selector:
                            try:
                                summary_element = await loop.run_in_executor(
                                    None,
                                    lambda: item.find_element(By.CSS_SELECTOR, summary_selector)
                                )
                                if summary_element:
                                    summary = await loop.run_in_executor(
                                        None,
                                        lambda: summary_element.text.strip()
                                    )
                            except Exception as summary_e:
                                logger.debug(f"提取摘要时出错: {str(summary_e)}")
                        
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
                                if content_element:
                                    content = await loop.run_in_executor(
                                        None,
                                        lambda: content_element.text.strip()
                                    )
                            except Exception as content_e:
                                logger.debug(f"提取内容时出错: {str(content_e)}")
                        
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
                    title = ""
                    title_element = None  # 确保在所有代码路径中初始化title_element
                    
                    # 首先检查所有链接，找出文本最长的一个（通常是标题）
                    a_elements = item.select('a[href]')
                    if a_elements:
                        # 找出所有有效的链接文本
                        link_texts = []
                        for a_elem in a_elements:
                            a_text = a_elem.get_text(strip=True)
                            # 跳过明显是分类的链接 [xxx] 或很短的链接
                            if (not re.match(r'^\[.*\]$', a_text)) and len(a_text) > 5 and not re.match(r'^\d{1,2}:\d{1,2}$', a_text):
                                link_texts.append((a_text, a_elem))
                        
                        # 找到最长的链接文本
                        if link_texts:
                            # 按文本长度排序
                            link_texts.sort(key=lambda x: len(x[0]), reverse=True)
                            title = link_texts[0][0]
                            title_element = link_texts[0][1]  # 保存链接元素为title_element
                            # 同时获取对应的链接URL
                            title_link = link_texts[0][1].get('href', '')
                            if title_link:
                                link = title_link
                            logger.info(f"从最长链接文本获取到标题: {title}")
                    
                    # 如果通过最长链接文本没有找到标题，再尝试标准方法
                    if not title and title_selector:
                        try:
                            # 查找标题元素
                            title_elements = item.select(title_selector)
                            if title_elements:
                                title_element = title_elements[0]
                                # 获取标题文本
                                title = title_element.get_text(strip=True)
                                
                                # 如果标题文本为空，尝试获取title属性
                                if not title:
                                    title = title_element.get('title', '')
                                
                                # 如果依然为空，尝试从父元素获取标题（通常是 a 标签）
                                if not title:
                                    # 查找包含当前元素的链接
                                    parent_link = title_element.find_parent('a')
                                    if parent_link:
                                        # 尝试从父链接获取title属性
                                        title = parent_link.get('title', '')
                                        
                                        # 如果父链接没有title属性，尝试获取其文本内容
                                        if not title:
                                            parent_text = parent_link.get_text(strip=True)
                                            title = parent_text
                        except Exception as e:
                            logger.warning(f"提取标题时出错: {str(e)}")
                    
                    # 如果使用所有方法后仍然为空，记录警告但不跳过此项
                    if not title:
                        title = f"未知标题 #{index+1}"
                        logger.warning(f"项目 {index} 的标题为空，使用默认标题: {title}")
                        # 额外调试日志，输出项目HTML以帮助排查
                        item_html = str(item)
                        logger.debug(f"项目 {index} HTML: {item_html[:500]}...")
                    
                    # 提取链接
                    link = ""
                    # 如果在标题提取时已经找到链接，这里就不需要再提取了
                    if 'link' not in locals() or not link:
                        if link_selector:
                            link_elements = item.select(link_selector)
                            if link_elements:
                                link = link_elements[0].get('href', '')
                        
                        # 如果找不到链接元素，尝试使用标题元素的href属性（如果title_element存在）
                        if not link and title_element is not None:
                            if title_element.name == 'a':
                                link = title_element.get('href', '')
                            else:
                                # 查找包含标题元素的链接
                                parent_link = title_element.find_parent('a')
                                if parent_link:
                                    link = parent_link.get('href', '')
                            
                            if link:
                                logger.info(f"项目 {index} 使用标题元素的href属性作为链接")
                        
                        # 如果仍然没有找到链接，尝试从所有链接中找到文本最长的链接
                        if not link and a_elements:
                            if len(a_elements) == 1:
                                link = a_elements[0].get('href', '')
                            else:
                                # 找出最可能是标题链接的那个（通常是文本最长的）
                                longest_text = ""
                                longest_link = ""
                                
                                for a_elem in a_elements:
                                    a_text = a_elem.get_text(strip=True)
                                    a_href = a_elem.get('href', '')
                                    
                                    # 排除分类链接、时间链接和其他明显不是标题的链接
                                    if (len(a_text) > len(longest_text) and 
                                        len(a_text) > 5 and 
                                        not re.match(r'^\[.*\]$', a_text) and 
                                        not re.match(r'^\d{1,2}:\d{1,2}$', a_text)):
                                        longest_text = a_text
                                        longest_link = a_href
                                
                                if longest_link:
                                    link = longest_link
                                    logger.info(f"项目 {index} 从最长链接文本获取到链接: {link}")
                                else:
                                    link = a_elements[0].get('href', '')
                        
                    # 如果仍然没有找到链接，则使用主URL
                    if not link:
                        link = self.url
                        logger.warning(f"项目 {index} 没有链接，使用源URL")
                    
                    # 处理相对URL
                    if link and not link.startswith(('http://', 'https://', '//')):
                        link = urljoin(self.url, link)
                    
                    # 提取发布日期
                    published_at = datetime.datetime.now()
                    if date_selector:
                        date_elements = item.select(date_selector)
                        if date_elements:
                            date_text = date_elements[0].get_text(strip=True)
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
                        
                    # 提取摘要
                    summary = ""
                    if summary_selector:
                        summary_elements = item.select(summary_selector)
                        if summary_elements:
                            summary = summary_elements[0].get_text(strip=True)
                    
                    # 如果没有摘要，则使用标题
                    if not summary:
                        summary = title
                    
                    # 提取内容
                    content = ""
                    if content_selector:
                        content_elements = item.select(content_selector)
                        if content_elements:
                            content = content_elements[0].get_text(strip=True)
                    
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
                    
                except Exception as item_e:
                    logger.warning(f"处理项目 {index} 时出错: {str(item_e)}")
                    import traceback
                    logger.debug(traceback.format_exc())
            
            logger.info(f"成功提取 {len(news_items)} 条新闻")
            return news_items
        
        except Exception as e:
            logger.error(f"解析HTML响应时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []

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