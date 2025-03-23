import logging
import datetime
import re
import hashlib
import os
import time
import random
import asyncio
import platform
import xml.etree.ElementTree as ET

from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

# Selenium相关导入
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as Service
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

# Global debug mode flag - set to False to reduce output
DEBUG_MODE = False

class V2EXSeleniumSource(WebNewsSource):
    """
    V2EX话题适配器 - Selenium版本
    
    特性:
    - 使用桌面版浏览器配置访问网站，避免被重定向到移动版
    - 通过Selenium模拟真实浏览器访问V2EX网站，绕过反爬虫措施
    - 支持从热门话题页面或XML feed获取数据
    - 使用大窗口尺寸和桌面版用户代理模拟真实桌面浏览器
    """
    
    # 用户代理列表，仅包含桌面浏览器，避免重定向到移动版网站
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Edge/120.0.0.0"
    ]
    
    def __init__(
        self,
        source_id: str = "v2ex",
        name: str = "V2EX热门",
        url: str = "https://www.v2ex.com/",  # 使用桌面版首页
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "technology",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        
        # 随机选择一个桌面版用户代理
        user_agent = random.choice(self.USER_AGENTS)
        
        # 确保URL是桌面版
        if url and "m.v2ex.com" in url:
            url = url.replace("m.v2ex.com", "www.v2ex.com")
            if DEBUG_MODE:
                logger.debug(f"URL已转换为桌面版: {url}")
        elif not url:
            url = "https://www.v2ex.com/"
            if DEBUG_MODE:
                logger.debug(f"使用默认桌面版URL: {url}")
        
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
            # 是否解析XML而不是HTML
            "parse_xml": False,
            # 调试配置
            "debug_file": "/tmp/v2ex_selenium_debug.html",  # 调试文件路径
            "failed_debug_file": "/tmp/v2ex_selenium_failed.html",  # 失败时的调试文件路径
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
        logger.info(f"初始化 {self.name} 适配器，URL: {self.url}")
    
    def _create_driver(self):
        """
        创建并配置Selenium WebDriver
        确保使用桌面版浏览器配置，避免被识别为爬虫
        """
        try:
            if DEBUG_MODE:
                logger.debug("开始创建Chrome WebDriver实例")
            chrome_options = Options()
            
            # 设置无头模式（不显示浏览器窗口）
            if self.config.get("headless", False):
                if DEBUG_MODE:
                    logger.debug("启用无头模式")
                chrome_options.add_argument("--headless=new")  # 使用新的无头模式
            
            # 设置桌面版用户代理
            user_agent = random.choice(self.USER_AGENTS)
            if DEBUG_MODE:
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
            
            # 使用webdriver-manager自动下载匹配的ChromeDriver
            try:
                # 尝试使用webdriver-manager自动下载匹配的ChromeDriver
                logger.info("使用webdriver-manager下载匹配的ChromeDriver")
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("成功创建Chrome WebDriver实例")
            except Exception as e:
                logger.warning(f"使用webdriver-manager失败: {str(e)}")
                
                # 尝试使用系统路径
                logger.info("尝试使用系统ChromeDriver路径")
                system = platform.system()
                if system == "Windows":
                    possible_paths = [
                        './resource/chromedriver.exe',
                        'C:\\Program Files\\Google\\Chrome\\Application\\chromedriver.exe',
                        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chromedriver.exe'
                    ]
                elif system == "Linux":
                    # 尝试多个可能的路径
                    possible_paths = [
                        '/usr/bin/chromedriver',
                        '/usr/local/bin/chromedriver',
                        '/snap/bin/chromedriver',
                        '/home/losesky/HeatLink/chromedriver'
                    ]
                else:  # macOS or other
                    possible_paths = [
                        '/usr/local/bin/chromedriver',
                        '/usr/bin/chromedriver'
                    ]
                
                # 查找第一个存在的ChromeDriver路径
                executable_path = None
                for path in possible_paths:
                    if os.path.exists(path):
                        executable_path = path
                        logger.info(f"找到ChromeDriver路径: {path}")
                        break
                
                if not executable_path:
                    # 如果没有找到，尝试直接使用默认的 'chromedriver'
                    executable_path = "chromedriver"
                    logger.info("使用系统PATH中的ChromeDriver")
                
                service = Service(executable_path=executable_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("成功创建Chrome WebDriver实例")
            
            # 设置页面加载超时
            driver.set_page_load_timeout(self.config.get("selenium_timeout", 30))
            
            # 设置脚本执行超时
            driver.set_script_timeout(self.config.get("selenium_timeout", 30))
            
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
                        logger.debug("WebDriver已正常关闭")
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
    
    async def close(self):
        """
        关闭桌面版浏览器资源
        """
        if DEBUG_MODE:
            logger.debug("关闭V2EX桌面版抓取资源")
        await self._close_driver()
        await super().close()
    
    async def _force_desktop_mode(self, driver, loop):
        """
        强制使用桌面模式，避免重定向到移动版
        """
        try:
            # 检查当前URL
            current_url = await loop.run_in_executor(None, lambda: driver.current_url)
            
            # 如果是移动版地址，转换回桌面版
            if "m.v2ex.com" in current_url:
                logger.warning(f"检测到移动版地址: {current_url}")
                
                # 转换为桌面版URL
                desktop_url = current_url.replace("m.v2ex.com", "www.v2ex.com")
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
                if "m.v2ex.com" in new_url:
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
    
    async def _fetch_with_selenium(self) -> str:
        """
        使用Selenium获取V2EX网页内容
        确保访问桌面版网站，避免被识别为爬虫
        """
        driver = await self._get_driver()
        if driver is None:
            logger.error("WebDriver创建失败")
            raise RuntimeError("无法获取V2EX数据：WebDriver创建失败")
        
        content = ""
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
            
            # 设置超时控制
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
                
                # 尝试使用JavaScript导航
                try:
                    logger.info("尝试使用JavaScript导航")
                    # 确保使用www子域名而不是m子域名
                    desktop_url = self.url.replace("m.v2ex.com", "www.v2ex.com")
                    await loop.run_in_executor(
                        None,
                        lambda: driver.execute_script(f"window.location.href = '{desktop_url}';")
                    )
                    
                    # 等待页面加载
                    await asyncio.sleep(10)
                    
                    # 强制使用桌面模式
                    await self._force_desktop_mode(driver, loop)
                except Exception as js_e:
                    logger.error(f"JavaScript导航失败: {str(js_e)}")
                    raise RuntimeError(f"无法获取V2EX数据：页面加载失败")
            
            # 等待页面加载完成
            await asyncio.sleep(5)
            
            # 等待页面元素加载
            try:
                await loop.run_in_executor(
                    None,
                    lambda: WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                )
            except Exception as wait_e:
                if DEBUG_MODE:
                    logger.debug(f"等待页面加载超时: {str(wait_e)}")
            
            # 获取页面内容
            try:
                content = await loop.run_in_executor(None, lambda: driver.page_source)
                
                # 保存页面源码供调试
                if DEBUG_MODE:
                    debug_file = self.config.get("debug_file", "/tmp/v2ex_selenium_debug.html")
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    logger.debug(f"页面源码已保存到: {debug_file}")
                
                # 检查是否是XML格式
                if content.strip().startswith('<?xml'):
                    logger.info("获取到XML内容")
                else:
                    logger.info("获取到HTML内容")
                
                # 检查是否有错误页面的特征
                if "访问频率过快" in content or "Access Denied" in content:
                    logger.warning("检测到访问限制页面，可能被认为是爬虫")
                    # 保存错误页面供分析
                    error_file = self.config.get("failed_debug_file", "/tmp/v2ex_selenium_failed.html")
                    with open(error_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    logger.warning(f"错误页面已保存到: {error_file}")
                
            except Exception as e:
                logger.error(f"获取页面内容失败: {str(e)}")
                raise RuntimeError(f"获取V2EX数据失败: {str(e)}")
            
            return content
            
        except Exception as e:
            logger.error(f"获取数据失败: {str(e)}")
            raise RuntimeError(f"获取数据失败: {str(e)}")
        finally:
            # 确保关闭driver
            await self._close_driver()

    def _unescape_content(self, content: str) -> str:
        """
        解码HTML和Unicode转义序列
        """
        if not content:
            return ""
        
        try:
            # 检查是否包含Unicode转义序列
            if r'\u003C' in content or r'\u003E' in content or r'\u' in content:
                logger.info("Detected Unicode escape sequences, unescaping content")
                
                # 定义替换函数
                def replace_unicode(match):
                    try:
                        # 获取Unicode码点
                        code_point = int(match.group(1), 16)
                        # 转换为字符
                        return chr(code_point)
                    except Exception as e:
                        logger.warning(f"Error unescaping Unicode sequence: {match.group(0)}, error: {str(e)}")
                        return match.group(0)
                
                # 使用正则表达式替换所有Unicode转义序列
                content = re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode, content)
                logger.debug(f"Content after unescaping Unicode sequences, length: {len(content)}")
            
            # 处理HTML实体
            content = content.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", "\"").replace("&apos;", "'")
            
            return content
        
        except Exception as e:
            logger.error(f"Error unescaping content: {str(e)}", exc_info=True)
            return content
    
    async def _parse_xml(self, xml_content: str) -> List[NewsItemModel]:
        """
        解析XML feed内容，提取新闻项
        """
        if not xml_content:
            logger.error("Empty XML content")
            return []
        
        try:
            news_items = []
            
            # 检查内容是否为XML格式
            xml_content = xml_content.strip()
            logger.debug(f"XML content starts with: {xml_content[:100]}...")
            
            # 处理可能的转义字符
            xml_content = self._unescape_content(xml_content)
            
            # 检查是否是HTML内容，如果是，尝试提取pre标签中的XML
            if not xml_content.startswith('<?xml') and not xml_content.startswith('<feed'):
                logger.info("Content does not start with XML declaration or feed element, trying to extract from HTML")
                # 尝试从页面中提取XML内容
                soup = BeautifulSoup(xml_content, 'html.parser')
                pre_tag = soup.find('pre')
                if pre_tag:
                    extracted_content = pre_tag.text.strip()
                    # 再次处理可能的转义字符
                    extracted_content = self._unescape_content(extracted_content)
                    logger.info(f"Extracted XML content from pre tag, length: {len(extracted_content)}")
                    # 将提取的内容赋值回xml_content变量
                    xml_content = extracted_content
                    logger.debug(f"Extracted XML content starts with: {xml_content[:100]}...")
                else:
                    logger.warning("Content is not in XML format and no pre tag found")
                    # 尝试直接查找feed元素
                    feed = soup.find('feed')
                    if feed:
                        logger.info("Found feed element directly in HTML, trying to parse")
                    else:
                        logger.error("No feed element found in HTML")
                        return []
            
            logger.info(f"Processing XML content, length: {len(xml_content)}")
            
            # 使用BeautifulSoup解析XML内容
            # 这比ElementTree更容忍格式问题
            try:
                soup = BeautifulSoup(xml_content, 'xml')
                entries = soup.find_all('entry')
                
                if not entries:
                    logger.warning("No entries found with BeautifulSoup XML parser")
                    # 尝试使用html.parser
                    soup = BeautifulSoup(xml_content, 'html.parser')
                    entries = soup.find_all('entry')
                    if not entries:
                        logger.error("No entries found with any parser")
                        return []
                
                logger.info(f"Found {len(entries)} entries with BeautifulSoup")
                
                for entry in entries:
                    try:
                        # 提取标题
                        title_elem = entry.find('title')
                        if title_elem is None or not title_elem.text:
                            logger.warning("Entry without title, skipping")
                            continue
                        
                        title = title_elem.text.strip()
                        logger.debug(f"Processing entry with title: {title}")
                        
                        # 提取链接
                        link_elem = entry.find('link', rel="alternate") or entry.find('link')
                        url = ""
                        if link_elem is not None:
                            if link_elem.get('href'):
                                url = link_elem.get('href')
                            elif link_elem.text:
                                url = link_elem.text.strip()
                        
                        if not url:
                            logger.warning(f"No URL found for entry: {title}")
                            continue  # 如果没有URL，跳过此条目
                        
                        # 确保URL是完整的
                        if url and not url.startswith('http'):
                            url = f"https://www.v2ex.com{url}"
                        
                        # 提取ID
                        id_elem = entry.find('id')
                        topic_id = ""
                        if id_elem is not None and id_elem.text:
                            id_text = id_elem.text.strip()
                            logger.debug(f"ID text: {id_text}")
                            if '/t/' in id_text:
                                topic_id = id_text.split('/t/')[-1].split('#')[0]
                        
                        # 如果无法从ID中提取，则从URL中提取
                        if not topic_id and url and '/t/' in url:
                            topic_id = url.split('/t/')[-1].split('#')[0]
                        
                        # 如果仍然无法提取，则生成一个基于URL的哈希ID
                        if not topic_id:
                            topic_id = hashlib.md5(url.encode()).hexdigest()
                        
                        logger.debug(f"Topic ID: {topic_id}")
                        
                        # 提取发布时间
                        published_at = datetime.datetime.now(datetime.timezone.utc)
                        published_elem = entry.find('published')
                        if published_elem is not None and published_elem.text:
                            try:
                                date_text = published_elem.text.strip()
                                logger.debug(f"Published date text: {date_text}")
                                # 处理Z结尾的ISO日期
                                if date_text.endswith('Z'):
                                    date_text = date_text.replace('Z', '+00:00')
                                published_at = datetime.datetime.fromisoformat(date_text)
                                logger.debug(f"Parsed published date: {published_at}")
                            except ValueError as e:
                                logger.warning(f"Invalid published date format: {published_elem.text}, error: {str(e)}")
                        
                        # 提取更新时间（如果没有发布时间）
                        if published_elem is None:
                            updated_elem = entry.find('updated')
                            if updated_elem is not None and updated_elem.text:
                                try:
                                    date_text = updated_elem.text.strip()
                                    logger.debug(f"Updated date text: {date_text}")
                                    if date_text.endswith('Z'):
                                        date_text = date_text.replace('Z', '+00:00')
                                    published_at = datetime.datetime.fromisoformat(date_text)
                                    logger.debug(f"Parsed updated date: {published_at}")
                                except ValueError as e:
                                    logger.warning(f"Invalid updated date format: {updated_elem.text}, error: {str(e)}")
                        
                        # 提取内容
                        content = ""
                        content_elem = entry.find('content')
                        if content_elem is not None:
                            if content_elem.text:
                                content = content_elem.text.strip()
                        # 检查是否有HTML内容
                        elif len(content_elem.contents) > 0:
                            content = str(content_elem.contents[0])
                        
                        # 如果没有content，尝试获取summary
                        if not content:
                            summary_elem = entry.find('summary')
                            if summary_elem is not None and summary_elem.text:
                                content = summary_elem.text.strip()
                        
                        # 提取作者
                        author = ""
                        author_elem = entry.find('author')
                        if author_elem is not None:
                            name_elem = author_elem.find('name')
                            if name_elem is not None and name_elem.text:
                                author = name_elem.text.strip()
                        
                        # 创建新闻项
                        news_item = self.create_news_item(
                            id=topic_id,
                            title=title,
                            url=url,
                            content=content,
                            author=author,
                            published_at=published_at
                        )
                        
                        news_items.append(news_item)
                        logger.debug(f"Added news item: {title}")
                    except Exception as e:
                        logger.error(f"Error processing entry: {str(e)}")
                
                logger.info(f"Processed {len(news_items)} news items from XML")
                return news_items
                
            except Exception as e:
                logger.error(f"Error parsing XML with BeautifulSoup: {str(e)}", exc_info=True)
            
        except Exception as e:
            logger.error(f"Error parsing XML: {str(e)}", exc_info=True)
            return []
    
    async def _parse_html(self, html_content: str) -> List[NewsItemModel]:
        """
        解析HTML内容，提取热门话题
        """
        if not html_content:
            logger.error("Empty HTML content")
            return []
        
        try:
            news_items = []
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 查找所有话题项
            topic_items = soup.select('div.cell.item')
            logger.debug(f"Found {len(topic_items)} topic items")
            
            for item in topic_items:
                try:
                    # 提取话题链接和标题
                    topic_link = item.select_one('span.item_title a.topic-link')
                    if not topic_link:
                        continue
                    
                    title = topic_link.get_text(strip=True)
                    url = topic_link.get('href')
                    if url and not url.startswith('http'):
                        url = f"https://www.v2ex.com{url}"
                    
                    # 提取话题ID
                    topic_id = ""
                    if url and '/t/' in url:
                        topic_id = url.split('/t/')[-1].split('#')[0]
                    else:
                        topic_id = hashlib.md5(url.encode()).hexdigest()
                    
                    # 提取节点信息
                    node = ""
                    node_link = item.select_one('a.node')
                    if node_link:
                        node = node_link.get_text(strip=True)
                    
                    # 从标题中提取节点信息（如果标题格式为 [节点] 标题）
                    if not node:
                        node_match = re.match(r'^\[(.*?)\]', title)
                        if node_match:
                            node = node_match.group(1)
                    
                    # 提取作者信息
                    author = ""
                    author_link = item.select_one('span.topic_info strong a')
                    if author_link:
                        author = author_link.get_text(strip=True)
                    
                    # 提取发布时间（V2EX页面上可能没有精确时间，使用相对时间）
                    published_at = datetime.datetime.now(datetime.timezone.utc)
                    time_span = item.select_one('span.topic_info span.ago')
                    if time_span:
                        time_text = time_span.get_text(strip=True)
                        # 尝试解析相对时间（如"1小时前"，"2天前"等）
                        # 这里只是简单处理，实际可能需要更复杂的解析
                        if '分钟前' in time_text:
                            minutes = int(re.search(r'(\d+)', time_text).group(1))
                            published_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)
                        elif '小时前' in time_text:
                            hours = int(re.search(r'(\d+)', time_text).group(1))
                            published_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
                        elif '天前' in time_text:
                            days = int(re.search(r'(\d+)', time_text).group(1))
                            published_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
                    
                    # 提取内容预览
                    content = ""
                    content_div = item.select_one('div.topic_content')
                    if content_div:
                        content = content_div.get_text(strip=True)
                    
                    # 如果没有内容预览，可能需要访问话题页面获取完整内容
                    # 这里简化处理，使用标题作为摘要
                    summary = content[:200] if content else title
                    
                    # 提取图片URL（如果有）
                    image_url = None
                    img_tag = item.select_one('img')
                    if img_tag and img_tag.has_attr('src'):
                        image_url = img_tag['src']
                        # 确保URL是完整的
                        if image_url and not image_url.startswith('http'):
                            image_url = f"https:{image_url}" if image_url.startswith('//') else f"https://www.v2ex.com{image_url}"
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=topic_id,
                        title=title,
                        url=url,
                        content=content,
                        summary=summary,
                        image_url=image_url,
                        published_at=published_at,
                        extra={
                            "is_top": False, 
                            "mobile_url": url,
                            "node": node,
                            "author": author,
                            "source": "v2ex"
                        }
                    )
                    
                    news_items.append(news_item)
                    logger.debug(f"Added news item from HTML: {title}")
                    
                except Exception as e:
                    logger.error(f"Error processing topic item: {str(e)}", exc_info=True)
                    continue
            
            logger.info(f"Parsed {len(news_items)} news items from V2EX HTML")
            return news_items
            
        except Exception as e:
            logger.error(f"Error parsing V2EX HTML: {str(e)}", exc_info=True)
            return []
    
    async def parse_response(self, response: str) -> List[NewsItemModel]:
        """
        根据内容类型选择合适的解析方法
        """
        if not response or len(response.strip()) == 0:
            logger.error("获取到空响应")
            return []
        
        # 检查是否是XML格式
        if response.strip().startswith('<?xml') or self.config.get("parse_xml", False):
            logger.info("解析XML内容")
            return await self._parse_xml(response)
        else:
            logger.info("解析HTML内容")
            return await self._parse_html(response)
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        获取V2EX热门话题
        
        Returns:
            热门话题列表
        """
        logger.info("获取V2EX数据")
        
        try:
            # 使用Selenium获取内容
            content = await self._fetch_with_selenium()
            
            # 解析内容
            news_items = await self.parse_response(content)
            
            if not news_items or len(news_items) == 0:
                logger.error("未获取到话题数据")
                raise RuntimeError("未获取到任何话题数据")
            
            logger.info(f"获取到 {len(news_items)} 条话题")
            return news_items
            
        except Exception as e:
            logger.error(f"获取数据失败: {str(e)}")
            raise RuntimeError(f"获取数据失败: {str(e)}")
        finally:
            # 确保每次fetch后都关闭driver，防止资源泄漏
            try:
                await self._close_driver()
            except Exception:
                pass 