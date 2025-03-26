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
try:
    # Import the custom logging configuration module
    from worker.sources.sites.thepaper_log_config import configure_thepaper_logging
    logger = configure_thepaper_logging()
except ImportError:
    # Fallback to standard logging if the config module is not available
    logger = logging.getLogger(__name__)
    # Set this logger to INFO to reduce output
    logger.setLevel(logging.INFO)
    # Set related loggers to WARNING
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

# Global debug mode flag - set to False to reduce output
DEBUG_MODE = False

# 跟踪已初始化的实例，确保一致性
_initialized_instances = {}
_initialized_source_ids = set()

class ThePaperSeleniumSource(WebNewsSource):
    """
    澎湃新闻热榜适配器 - Selenium版本
    专门使用Selenium从澎湃新闻网站获取热榜数据
    通过分析页面结构直接提取新闻列表
    
    特性:
    - 使用桌面版浏览器配置访问网站，避免被重定向到移动版
    - 监测并自动从移动版切换到桌面版，确保获取完整内容
    - 使用大窗口尺寸和桌面版用户代理模拟真实桌面浏览器
    - 使用缓存机制减少频繁请求和Selenium会话开销
    - 通过超时控制避免任务长时间阻塞
    """
    
    # 用户代理列表，仅包含桌面浏览器，避免重定向到移动版网站
    # 明确使用桌面版用户代理，避免被重定向到移动版，确保获取完整桌面版内容
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Edge/120.0.0.0"
    ]
    
    def __init__(
        self,
        source_id: str = "thepaper",
        name: str = "澎湃新闻热榜",
        url: str = "https://www.thepaper.cn/",
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "news",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        # 强制统一source_id，避免混乱
        if source_id != "thepaper":
            logger.warning(f"源ID '{source_id}' 被统一为标准ID 'thepaper'")
            source_id = "thepaper"
        
        # 检查是否已经有同ID的实例初始化
        instance_key = source_id
        
        if instance_key in _initialized_instances:
            instance_count = _initialized_instances[instance_key]
            _initialized_instances[instance_key] = instance_count + 1
            logger.warning(f"注意：{source_id} 适配器正在被重复初始化，这是第 {instance_count+1} 次初始化")
            
            # 记录调用栈，帮助诊断重复初始化来源
            import traceback
            stack_trace = ''.join(traceback.format_stack()[:-1])
            logger.debug(f"初始化调用栈:\n{stack_trace}")
        else:
            _initialized_instances[instance_key] = 1
            _initialized_source_ids.add(source_id)
        
        config = config or {}
        
        # 随机选择一个桌面版用户代理
        user_agent = random.choice(self.USER_AGENTS)
        
        # 确保URL是桌面版
        if url and ("m.thepaper.cn" in url or "mobile.thepaper.cn" in url):
            url = url.replace("m.thepaper.cn", "www.thepaper.cn").replace("mobile.thepaper.cn", "www.thepaper.cn")
            logger.info(f"URL已转换为桌面版: {url}")
        elif not url:
            url = "https://www.thepaper.cn/"
            logger.info(f"使用默认桌面版URL: {url}")
        
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
            # Selenium配置
            "use_selenium": True,  # 始终启用Selenium
            "selenium_timeout": 20,  # 降低页面加载超时时间（秒）
            "selenium_wait_time": 3,  # 降低等待元素出现的时间（秒）
            "headless": True,  # 无头模式（不显示浏览器窗口）
            # 重试配置
            "max_retries": 2,       # 减少重试次数以提高速度
            "retry_delay": 2,       # 减少重试延迟
            # 启用缓存以减少重复请求
            "use_cache": True,
            "cache_ttl": 1800,      # 30分钟缓存
            # 启用随机延迟，避免被识别为爬虫
            "use_random_delay": True,
            "min_delay": 0.5,       # 减少最小延迟
            "max_delay": 1.5,       # 减少最大延迟
            # 整体超时控制
            "overall_timeout": 60,  # 整体操作超时时间（秒）
            # 调试配置
            "debug_file": "/tmp/thepaper_selenium_debug.html",  # 调试文件路径
            "failed_debug_file": "/tmp/thepaper_selenium_failed.html",  # 失败时的调试文件路径
            # HTTP备用方式
            "use_http_fallback": True,  # 启用HTTP备用方式
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
        
        # 增加内存缓存
        self._news_cache = []
        self._last_cache_update = 0
        self._cache_ttl = 1800  # 30分钟缓存有效期
        self._cache_lock = asyncio.Lock()
        
        # 已尝试了HTTP备用的标志
        self._tried_http_fallback = False
    
    def _create_driver(self):
        """
        创建并配置Selenium WebDriver
        确保使用桌面版浏览器配置，避免被重定向到移动版站点
        """
        try:
            logger.debug("开始创建Chrome WebDriver实例")
            chrome_options = Options()
            
            # 设置无头模式（不显示浏览器窗口）
            if self.config.get("headless", False):
                logger.debug("启用无头模式")
                chrome_options.add_argument("--headless=new")  # 使用新的无头模式
            
            # 设置桌面版用户代理
            user_agent = random.choice(self.USER_AGENTS)
            logger.debug(f"使用桌面版用户代理: {user_agent}")
            chrome_options.add_argument(f"--user-agent={user_agent}")
            
            # 设置桌面级别的窗口大小，确保网站认为这是桌面浏览器
            chrome_options.add_argument("--window-size=1920,1080")
            
            # 禁用移动仿真
            chrome_options.add_experimental_option("mobileEmulation", {})
            
            # 明确设置为桌面模式
            chrome_options.add_argument("--disable-device-emulation")
            chrome_options.add_argument("--start-maximized")
            
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
            
            # 启用JavaScript
            chrome_options.add_argument("--enable-javascript")
            
            # 设置语言
            chrome_options.add_argument("--lang=zh-CN")
            
            # 设置接受Cookie
            chrome_options.add_argument("--enable-cookies")
            
            # 使用系统的ChromeDriver
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
                    # 这会使用系统PATH中的ChromeDriver
                    chromedriver_path = "chromedriver"
                    logger.info("使用系统PATH中的ChromeDriver")
                
                # 创建服务和WebDriver
                service = Service(executable_path=chromedriver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("成功创建Chrome WebDriver实例")
                
                # 记录driver进程ID，用于后续清理
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
                logger.error(f"使用系统ChromeDriver失败: {str(driver_e)}", exc_info=True)
                
                # 尝试手动搜索Chrome和ChromeDriver可执行文件
                try:
                    logger.info("尝试搜索Chrome和ChromeDriver可执行文件...")
                    
                    # 运行命令以查找Chrome和ChromeDriver
                    import subprocess
                    
                    # 查找Chrome
                    chrome_paths = subprocess.run(
                        "which google-chrome chromium-browser chromium chrome 2>/dev/null || echo ''", 
                        shell=True, 
                        capture_output=True, 
                        text=True
                    ).stdout.strip().split('\n')
                    
                    if chrome_paths and chrome_paths[0]:
                        chrome_path = chrome_paths[0]
                        logger.info(f"找到Chrome浏览器路径: {chrome_path}")
                        
                        # 设置Chrome路径
                        chrome_options.binary_location = chrome_path
                    
                    # 查找ChromeDriver
                    chromedriver_paths = subprocess.run(
                        "which chromedriver 2>/dev/null || echo ''", 
                        shell=True, 
                        capture_output=True, 
                        text=True
                    ).stdout.strip().split('\n')
                    
                    if chromedriver_paths and chromedriver_paths[0]:
                        chromedriver_path = chromedriver_paths[0]
                        logger.info(f"找到ChromeDriver路径: {chromedriver_path}")
                        
                        # 创建服务和WebDriver
                        service = Service(executable_path=chromedriver_path)
                        driver = webdriver.Chrome(service=service, options=chrome_options)
                        logger.info("成功使用搜索到的ChromeDriver创建WebDriver实例")
                        
                        # 设置页面加载超时
                        driver.set_page_load_timeout(self.config.get("selenium_timeout", 30))
                        
                        # 设置脚本执行超时
                        driver.set_script_timeout(self.config.get("selenium_timeout", 30))
                        
                        return driver
                    else:
                        logger.error("未找到ChromeDriver可执行文件")
                        
                except Exception as search_e:
                    logger.error(f"搜索Chrome和ChromeDriver失败: {str(search_e)}", exc_info=True)
                
                # 如果所有方法都失败，尝试通过命令行安装ChromeDriver
                try:
                    logger.info("尝试通过命令行安装最新版本的ChromeDriver...")
                    
                    # 运行命令以安装/更新ChromeDriver
                    import subprocess
                    
                    # 在Linux上尝试安装ChromeDriver
                    if platform.system() == "Linux":
                        # 创建安装目录
                        os.makedirs('/home/losesky/HeatLink/chromedriver-install', exist_ok=True)
                        
                        # 下载最新的ChromeDriver
                        install_cmd = """
                        cd /home/losesky/HeatLink/chromedriver-install && 
                        wget -q -O chromedriver_linux64.zip https://chromedriver.storage.googleapis.com/LATEST_RELEASE && 
                        latest_version=$(cat LATEST_RELEASE) &&
                        wget -q -O chromedriver_linux64.zip https://chromedriver.storage.googleapis.com/${latest_version}/chromedriver_linux64.zip && 
                        unzip -o chromedriver_linux64.zip && 
                        chmod +x chromedriver && 
                        mv chromedriver /home/losesky/HeatLink/chromedriver
                        """
                        
                        subprocess.run(install_cmd, shell=True, check=True)
                        logger.info("成功下载并安装最新版本的ChromeDriver")
                        
                        # 使用新安装的ChromeDriver
                        chromedriver_path = '/home/losesky/HeatLink/chromedriver'
                        service = Service(executable_path=chromedriver_path)
                        driver = webdriver.Chrome(service=service, options=chrome_options)
                        logger.info("成功使用新安装的ChromeDriver创建WebDriver实例")
                        
                        # 设置页面加载超时和脚本执行超时
                        driver.set_page_load_timeout(self.config.get("selenium_timeout", 30))
                        driver.set_script_timeout(self.config.get("selenium_timeout", 30))
                        
                        return driver
                
                except Exception as install_e:
                    logger.error(f"安装ChromeDriver失败: {str(install_e)}", exc_info=True)
                
                # 如果所有方法都失败，再次尝试使用webdriver_manager作为最后的手段
                try:
                    logger.info("最后尝试使用webdriver_manager...")
                    from webdriver_manager.chrome import ChromeDriverManager
                    
                    service = Service(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                    logger.info("成功使用webdriver_manager创建WebDriver实例")
                    
                    # 设置页面加载超时和脚本执行超时
                    driver.set_page_load_timeout(self.config.get("selenium_timeout", 30))
                    driver.set_script_timeout(self.config.get("selenium_timeout", 30))
                    
                    return driver
                    
                except Exception as wdm_e:
                    logger.error(f"使用webdriver_manager失败: {str(wdm_e)}", exc_info=True)
                
                raise Exception("无法创建Chrome WebDriver: 所有方法都失败")
                
        except Exception as e:
            logger.error(f"创建Chrome WebDriver时出错: {str(e)}", exc_info=True)
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
        获取新闻
        通过Selenium访问网站获取，如果失败则尝试使用HTTP请求备用方案
        增加了缓存机制和超时控制，极大减少响应时间
        """
        logger.info(f"开始获取澎湃新闻热榜数据")
        start_time = time.time()
        
        # 首先检查缓存是否有效
        current_time = time.time()
        if self._news_cache and current_time - self._last_cache_update < self._cache_ttl:
            logger.info(f"从缓存获取到 {len(self._news_cache)} 条澎湃新闻热榜数据，用时: {time.time() - start_time:.2f}秒")
            # 从缓存获取不需要更新统计，注释掉以避免重复统计
            # try:
            #     from worker.stats_wrapper import stats_updater
            #     # 创建一个假的fetch函数，确保外部API调用计数增加
            #     async def dummy_fetch():
            #         return self._news_cache.copy()
            #     # 带上外部API类型标记包装这个假函数并执行
            #     await stats_updater.wrap_fetch(self.source_id, dummy_fetch, api_type="external")
            # except Exception as stats_e:
            #     logger.warning(f"更新澎湃新闻热榜外部API统计时出错: {str(stats_e)}")
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
                logger.info(f"成功获取 {len(news_items)} 条澎湃新闻热榜数据，用时: {elapsed:.2f}秒")
                
                # 更新缓存
                async with self._cache_lock:
                    self._news_cache = news_items
                    self._last_cache_update = time.time()
                
                # 注释掉以避免重复统计，因为实际的fetch_impl内部已经更新了统计
                # try:
                #     from worker.stats_wrapper import stats_updater
                #     # 创建一个假的fetch函数，确保外部API调用计数增加
                #     async def dummy_fetch():
                #         return news_items
                #     # 包装这个假函数并执行
                #     await stats_updater.wrap_fetch(self.source_id, dummy_fetch, api_type="external")
                # except Exception as stats_e:
                #     logger.warning(f"更新澎湃新闻热榜外部API统计时出错: {str(stats_e)}")
                
                return news_items
            except asyncio.TimeoutError:
                logger.warning(f"获取澎湃新闻热榜数据超时 ({overall_timeout}秒)，尝试使用备用方法")
                
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
                            
                            # HTTP备用方法是真正的外部调用，需要更新统计
                            try:
                                from worker.stats_wrapper import stats_updater
                                # 创建一个假的fetch函数
                                async def dummy_fetch():
                                    return fallback_items
                                # 包装这个假函数并执行，这里可以保留因为HTTP fallback是额外的API调用
                                await stats_updater.wrap_fetch(self.source_id, dummy_fetch, api_type="external")
                            except Exception as stats_e:
                                logger.warning(f"更新澎湃新闻热榜外部API统计时出错: {str(stats_e)}")
                            
                            return fallback_items
                    except Exception as fallback_e:
                        logger.error(f"HTTP备用方法失败: {str(fallback_e)}")
                
                # 如果有缓存，返回缓存
                if self._news_cache:
                    logger.info(f"返回缓存的 {len(self._news_cache)} 条新闻")
                    # 从缓存获取不需要更新统计
                    # try:
                    #     from worker.stats_wrapper import stats_updater
                    #     # 创建一个假的fetch函数
                    #     async def dummy_fetch():
                    #         return self._news_cache.copy()
                    #     # 包装这个假函数并执行
                    #     await stats_updater.wrap_fetch(self.source_id, dummy_fetch, api_type="external")
                    # except Exception as stats_e:
                    #     logger.warning(f"更新澎湃新闻热榜外部API统计时出错: {str(stats_e)}")
                    return self._news_cache.copy()
                
                logger.error("获取澎湃新闻热榜数据完全失败")
                return []
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"获取澎湃新闻热榜数据时发生错误: {str(e)}，用时: {elapsed:.2f}秒")
            
            # 如果有缓存，返回缓存
            if self._news_cache:
                logger.info(f"错误后返回缓存的 {len(self._news_cache)} 条新闻")
                # 从缓存获取不需要更新统计
                # try:
                #     from worker.stats_wrapper import stats_updater
                #     # 创建一个假的fetch函数
                #     async def dummy_fetch():
                #         return self._news_cache.copy()
                #     # 包装这个假函数并执行
                #     await stats_updater.wrap_fetch(self.source_id, dummy_fetch, api_type="external")
                # except Exception as stats_e:
                #     logger.warning(f"更新澎湃新闻热榜外部API统计时出错: {str(stats_e)}")
                return self._news_cache.copy()
            
            raise
    
    async def _fetch_impl(self) -> List[NewsItemModel]:
        """实际获取数据的内部方法"""
        # 重置HTTP备用标志
        self._tried_http_fallback = False
        
        # 先尝试使用Selenium获取
        try:
            return await self._fetch_with_selenium()
        except Exception as e:
            logger.error(f"使用Selenium获取澎湃新闻热榜数据失败: {str(e)}")
            
            # 尝试HTTP备用方法
            if self.config.get("use_http_fallback", True):
                logger.info("尝试使用HTTP备用方法获取数据")
                try:
                    fallback_items = await self._fetch_with_http_fallback()
                    if fallback_items:
                        logger.info(f"通过HTTP备用方法成功获取 {len(fallback_items)} 条新闻")
                        return fallback_items
                except Exception as fallback_e:
                    logger.error(f"HTTP备用方法失败: {str(fallback_e)}")
            
            # 如果都失败，抛出异常
            raise
    
    async def _fetch_with_http_fallback(self) -> List[NewsItemModel]:
        """使用HTTP请求作为备用方案获取新闻"""
        logger.info("使用HTTP请求作为备用方案获取澎湃新闻热榜数据")
        
        try:
            # 获取HTTP客户端
            client = http_client
            
            # 准备请求头
            headers = {
                "User-Agent": random.choice(self.USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://www.thepaper.cn/",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            }
            
            # 尝试获取首页
            async with client.get("https://www.thepaper.cn/", headers=headers, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"HTTP备用方法获取首页失败，状态码: {response.status}")
                    return []
                
                content = await response.text()
                
                # 解析HTML
                soup = BeautifulSoup(content, 'html.parser')
                
                # 提取新闻列表
                news_items = []
                
                # 尝试提取热榜新闻
                hot_news_section = soup.select_one(".news_li, .news-list, .hot-list")
                if hot_news_section:
                    news_links = hot_news_section.select("a")
                    for idx, link in enumerate(news_links[:30]):  # 限制数量
                        try:
                            href = link.get("href", "")
                            if not href or href == "#" or "javascript:" in href:
                                continue
                                
                            # 构建完整URL
                            if href.startswith("/"):
                                full_url = f"https://www.thepaper.cn{href}"
                            elif href.startswith("http"):
                                full_url = href
                            else:
                                full_url = f"https://www.thepaper.cn/{href}"
                            
                            # 提取标题
                            title = link.get_text(strip=True)
                            if not title and link.select_one(".title, h3, h4"):
                                title = link.select_one(".title, h3, h4").get_text(strip=True)
                            
                            if not title:
                                continue
                            
                            # 生成唯一ID
                            # 从URL提取ID或使用标题哈希
                            match = re.search(r'newsDetail_forward_(\d+)', href)
                            if match:
                                id_part = match.group(1)
                            else:
                                id_part = hashlib.md5(title.encode()).hexdigest()
                            
                            item_id = f"thepaper-http-{id_part}"
                            
                            # 创建新闻项
                            news_item = NewsItemModel(
                                id=item_id,
                                title=title,
                                url=full_url,
                                source_id=self.source_id,
                                source_name=self.name,
                                published_at=datetime.datetime.now(),  # 无法获取准确时间，使用当前时间
                                category=self.category,
                                language=self.language,
                                country=self.country,
                                extra={
                                    "rank": idx + 1,
                                    "fetched_by": "http_fallback"
                                }
                            )
                            
                            news_items.append(news_item)
                        except Exception as e:
                            logger.error(f"解析新闻项失败: {str(e)}")
                
                logger.info(f"通过HTTP备用方法获取到 {len(news_items)} 条新闻")
                return news_items
        except Exception as e:
            logger.error(f"HTTP备用方法失败: {str(e)}")
            raise
    
    # 清理缓存
    async def clear_cache(self):
        """清理缓存数据"""
        async with self._cache_lock:
            self._news_cache = []
            self._last_cache_update = 0
        logger.info("已清理澎湃新闻热榜缓存")
    
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

    async def _fetch_with_selenium(self) -> List[NewsItemModel]:
        """
        使用Selenium从澎湃新闻获取数据
        
        确保访问桌面版网站，避免被重定向到移动版
        """
        logger.info("获取澎湃新闻数据")
        driver = await self._get_driver()
        if driver is None:
            logger.error("WebDriver创建失败")
            raise RuntimeError("无法获取澎湃新闻数据：WebDriver创建失败")
        
        news_items = []
        try:
            # 随机延迟，模拟人类行为
            if self.config.get("use_random_delay", True):
                delay = random.uniform(
                    self.config.get("min_delay", 1.0),
                    self.config.get("max_delay", 3.0)
                )
                if DEBUG_MODE:
                    logger.debug(f"请求前随机延迟: {delay:.2f} 秒")
                await asyncio.sleep(delay)
            
            # 访问页面
            logger.info(f"访问URL: {self.url}")
            loop = asyncio.get_event_loop()
            
            # 使用超时控制
            try:
                page_load_timeout = self.config.get("selenium_timeout", 30)
                
                # 设置超时
                await loop.run_in_executor(
                    None, 
                    lambda: driver.set_page_load_timeout(page_load_timeout)
                )
                
                # 访问URL
                start_time = time.time()
                await loop.run_in_executor(None, lambda: driver.get(self.url))
                end_time = time.time()
                if DEBUG_MODE:
                    logger.debug(f"页面加载耗时: {end_time - start_time:.2f} 秒")
                
                # 强制使用桌面模式
                switched = await self._force_desktop_mode(driver, loop)
                if switched:
                    logger.info("已切换到桌面模式")
                
            except Exception as e:
                logger.warning(f"页面加载异常: {str(e)}")
                
                # 尝试使用JavaScript导航（可能绕过某些超时问题）
                try:
                    logger.info("尝试使用JavaScript导航")
                    # 确保使用www子域名而不是m子域名
                    desktop_url = self.url.replace("m.thepaper.cn", "www.thepaper.cn")
                    await loop.run_in_executor(
                        None,
                        lambda: driver.execute_script(f"window.location.href = '{desktop_url}';")
                    )
                    
                    # 等待页面加载
                    await asyncio.sleep(10)
                    
                    # 强制使用桌面模式
                    await self._force_desktop_mode(driver, loop)
                except Exception as js_e:
                    logger.error(f"导航失败: {str(js_e)}")
                    raise RuntimeError(f"无法获取澎湃新闻数据：页面加载失败")
            
            # 等待页面加载完成
            await asyncio.sleep(5)
            
            # 使用等待确保页面完全加载
            try:
                await loop.run_in_executor(
                    None,
                    lambda: WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                )
            except Exception as wait_e:
                if DEBUG_MODE:
                    logger.warning(f"等待页面加载超时: {str(wait_e)}")
            
            # 保存页面源码供调试
            if DEBUG_MODE:
                try:
                    page_source = await loop.run_in_executor(None, lambda: driver.page_source)
                    debug_file = self.config.get("debug_file", "/tmp/thepaper_selenium_debug.html")
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write(page_source)
                    logger.debug(f"页面源码已保存: {debug_file}")
                except Exception as src_e:
                    logger.warning(f"保存页面源码失败: {str(src_e)}")
            
            # 尝试根据用户提供的特定HTML结构获取新闻列表
            logger.info("开始提取新闻数据")
            try:
                # 查找方法1: 直接查找热榜容器
                news_items = await self._find_news_from_hot_container(driver, loop)
                if news_items and len(news_items) > 0:
                    logger.info(f"从热榜容器获取到 {len(news_items)} 条新闻")
                    return news_items
                
                # 查找方法2: 查找新闻卡片元素
                news_items = await self._find_news_from_cards(driver, loop)
                if news_items and len(news_items) > 0:
                    logger.info(f"从新闻卡片获取到 {len(news_items)} 条新闻")
                    return news_items
                
                # 查找方法3: 尝试查找所有链接到新闻详情的元素
                news_items = await self._find_news_from_all_links(driver, loop)
                if news_items and len(news_items) > 0:
                    logger.info(f"从链接获取到 {len(news_items)} 条新闻")
                    return news_items
                
                # 如果以上方法都失败，尝试截图以供分析
                if DEBUG_MODE:
                    try:
                        screenshot_path = "/tmp/thepaper_debug_screenshot.png"
                        await loop.run_in_executor(
                            None,
                            lambda: driver.save_screenshot(screenshot_path)
                        )
                        logger.debug(f"已保存截图: {screenshot_path}")
                    except Exception:
                        pass
                
                raise RuntimeError("未找到新闻元素")
                
            except Exception as extract_e:
                logger.error(f"提取新闻失败: {str(extract_e)}")
                raise RuntimeError(f"提取新闻失败: {str(extract_e)}")
                
        except Exception as e:
            logger.error(f"获取数据失败: {str(e)}")
            raise RuntimeError(f"获取数据失败: {str(e)}")
        finally:
            # 确保关闭driver
            await self._close_driver()

    async def _find_news_from_hot_container(self, driver, loop) -> List[NewsItemModel]:
        """
        通过热榜容器获取新闻数据
        """
        if DEBUG_MODE:
            logger.debug("查找热榜容器")
        news_items = []
        
        try:
            # 1. 首先尝试找到热榜容器 - 使用用户提供的类名
            try:
                # 尝试查找热榜顶部容器
                hot_news_containers = await loop.run_in_executor(
                    None,
                    lambda: driver.find_elements(By.CSS_SELECTOR, "div.index_rebangtop__tpSSj")
                )
                
                if hot_news_containers:
                    if DEBUG_MODE:
                        logger.debug(f"找到热榜顶部容器: {len(hot_news_containers)} 个")
                    
                    # 2. 查找内容容器
                    content_containers = await loop.run_in_executor(
                        None,
                        lambda: driver.find_elements(By.CSS_SELECTOR, "div.index_content___Uhtm")
                    )
                    
                    if content_containers:
                        if DEBUG_MODE:
                            logger.debug(f"找到内容容器: {len(content_containers)} 个")
                        content_container = content_containers[0]
                        
                        # 3. 从内容容器中获取新闻列表项
                        news_links = await loop.run_in_executor(
                            None,
                            lambda: content_container.find_elements(By.CSS_SELECTOR, "li div.mdCard a")
                        )
                        
                        if not news_links:
                            # 尝试不同的选择器
                            news_links = await loop.run_in_executor(
                                None,
                                lambda: content_container.find_elements(By.CSS_SELECTOR, "a.index_inherit__A1ImK")
                            )
                        
                        if DEBUG_MODE:
                            logger.debug(f"找到新闻链接: {len(news_links)} 个")
                        
                        # 4. 处理每个新闻项
                        extracted_count = 0
                        for index, link in enumerate(news_links[:30]):  # 最多处理前30个
                            try:
                                # 获取链接
                                url = await loop.run_in_executor(
                                    None,
                                    lambda: link.get_attribute('href')
                                )
                                
                                # 获取标题
                                title = await loop.run_in_executor(
                                    None,
                                    lambda: link.text.strip()
                                )
                                
                                # 如果没有标题文本，尝试获取title属性
                                if not title:
                                    title = await loop.run_in_executor(
                                        None,
                                        lambda: link.get_attribute('title')
                                    )
                                
                                # 确保URL和标题不为空
                                if not url or not title:
                                    if DEBUG_MODE:
                                        logger.debug(f"跳过无效项 #{index}: URL={url}, 标题={title}")
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
                                extracted_count += 1
                                if DEBUG_MODE and index < 3:  # 仅记录前3个
                                    logger.debug(f"提取新闻: {title}")
                            except Exception as item_e:
                                if DEBUG_MODE:
                                    logger.debug(f"处理元素 {index} 失败: {str(item_e)}")
                        
                        if DEBUG_MODE and extracted_count > 0:
                            logger.debug(f"共提取 {extracted_count} 条新闻")
                                
            except Exception as se_e:
                if DEBUG_MODE:
                    logger.debug(f"查找热榜容器异常: {str(se_e)}")
        
        except Exception as e:
            if DEBUG_MODE:
                logger.debug(f"提取热榜新闻异常: {str(e)}")
        
        return news_items

    async def _find_news_from_cards(self, driver, loop) -> List[NewsItemModel]:
        """
        查找所有新闻卡片元素获取数据
        """
        logger.info("尝试查找所有新闻卡片元素")
        news_items = []
        
        try:
            # 尝试直接查找所有mdCard元素
            card_elements = await loop.run_in_executor(
                None,
                lambda: driver.find_elements(By.CSS_SELECTOR, "div.mdCard")
            )
            
            if card_elements:
                logger.info(f"找到 {len(card_elements)} 个mdCard元素")
                
                for index, card in enumerate(card_elements[:30]):
                    try:
                        # 在卡片中查找链接
                        link = await loop.run_in_executor(
                            None,
                            lambda: card.find_element(By.TAG_NAME, "a")
                        )
                        
                        # 获取链接
                        url = await loop.run_in_executor(
                            None,
                            lambda: link.get_attribute('href')
                        )
                        
                        # 获取标题
                        title = await loop.run_in_executor(
                            None,
                            lambda: link.text.strip()
                        )
                        
                        # 如果没有标题文本，尝试获取title属性
                        if not title:
                            title = await loop.run_in_executor(
                                None,
                                lambda: link.get_attribute('title')
                            )
                        
                        # 确保URL和标题不为空
                        if not url or not title:
                            logger.warning(f"卡片 {index} 缺少URL或标题: URL={url}, 标题={title}")
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
                        logger.error(f"处理卡片 {index} 时出错: {str(item_e)}")
        
        except Exception as e:
            logger.error(f"查找新闻卡片元素时出错: {str(e)}")
        
        return news_items

    async def _find_news_from_all_links(self, driver, loop) -> List[NewsItemModel]:
        """
        查找所有新闻详情链接
        """
        logger.info("尝试查找所有新闻详情链接")
        news_items = []
        
        try:
            # 查找所有新闻详情链接
            news_links = await loop.run_in_executor(
                None,
                lambda: driver.find_elements(By.CSS_SELECTOR, "a[href*='newsDetail']")
            )
            
            if news_links:
                logger.info(f"找到 {len(news_links)} 个新闻详情链接")
                
                # 按位置排序
                def get_y_position(element):
                    try:
                        # 获取元素位置
                        location = element.location
                        return location['y']
                    except:
                        return 0
                
                # 尝试按垂直位置排序（可以帮助确定热榜顺序）
                try:
                    news_links.sort(key=get_y_position)
                except Exception as sort_e:
                    logger.warning(f"排序链接时出错: {str(sort_e)}")
                
                # 处理每个链接
                for index, link in enumerate(news_links[:30]):
                    try:
                        # 获取链接
                        url = await loop.run_in_executor(
                            None,
                            lambda: link.get_attribute('href')
                        )
                        
                        # 获取标题
                        title = await loop.run_in_executor(
                            None,
                            lambda: link.text.strip()
                        )
                        
                        # 如果没有标题文本，尝试获取title属性
                        if not title:
                            title = await loop.run_in_executor(
                                None,
                                lambda: link.get_attribute('title')
                            )
                        
                        # 确保URL和标题不为空
                        if not url or not title:
                            logger.warning(f"链接 {index} 缺少URL或标题: URL={url}, 标题={title}")
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
                        logger.error(f"处理链接 {index} 时出错: {str(item_e)}")
        
        except Exception as e:
            logger.error(f"查找新闻详情链接时出错: {str(e)}")
        
        return news_items

    async def _force_desktop_mode(self, driver, loop):
        """
        强制使用桌面模式，避免重定向到移动版
        """
        try:
            # 检查当前URL
            current_url = await loop.run_in_executor(None, lambda: driver.current_url)
            
            # 如果是移动版地址，转换回桌面版
            if "m.thepaper.cn" in current_url:
                logger.warning(f"检测到移动版地址: {current_url}")
                
                # 转换为桌面版URL
                desktop_url = current_url.replace("m.thepaper.cn", "www.thepaper.cn")
                logger.info(f"尝试切换到桌面版: {desktop_url}")
                
                # 设置强制使用桌面用户代理
                desktop_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                await loop.run_in_executor(
                    None,
                    lambda: driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": desktop_agent})
                )
                
                # 清除所有cookie（可能包含移动版偏好设置）
                await loop.run_in_executor(None, lambda: driver.delete_all_cookies())
                
                # 访问桌面版URL
                await loop.run_in_executor(None, lambda: driver.get(desktop_url))
                
                # 等待页面加载
                await asyncio.sleep(3)
                
                # 再次检查URL
                new_url = await loop.run_in_executor(None, lambda: driver.current_url)
                if "m.thepaper.cn" in new_url:
                    # 如果仍然是移动版，使用JavaScript强制导航
                    logger.warning("仍处于移动版，尝试使用JavaScript强制导航")
                    await loop.run_in_executor(
                        None,
                        lambda: driver.execute_script(f"window.location.href = '{desktop_url}';")
                    )
                    await asyncio.sleep(3)  # 再次等待加载
                
                # 设置大窗口尺寸，进一步确保桌面体验
                await loop.run_in_executor(
                    None,
                    lambda: driver.set_window_size(1920, 1080)
                )
                
                return True  # 表示进行了桌面模式切换
            
            return False  # 表示无需切换
            
        except Exception as e:
            logger.warning(f"强制桌面模式失败: {str(e)}")
            return False 

    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        实现基类要求的parse_response方法
        
        由于ThePaperSeleniumSource类使用Selenium和自定义的fetch方法进行数据获取和解析，
        这个方法仅作为满足抽象基类要求而存在，实际不会被直接调用。
        实际的解析逻辑在_fetch_with_selenium和相关方法中。
        
        Args:
            response: HTML响应内容
            
        Returns:
            空列表，因为该方法不会被实际使用
        """
        logger.warning("ThePaperSeleniumSource.parse_response被直接调用，这不是预期的使用方式。"
                      "ThePaper适配器使用专用的Selenium方法获取新闻。")
        return [] 