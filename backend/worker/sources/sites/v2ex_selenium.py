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


class V2EXSeleniumSource(WebNewsSource):
    """
    V2EX话题适配器 - Selenium版本
    通过Selenium模拟真实浏览器访问V2EX网站，绕过反爬虫措施
    支持从热门话题页面或XML feed获取数据
    """
    
    # 用户代理列表，模拟不同的浏览器
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
    ]
    
    def __init__(
        self,
        source_id: str = "v2ex",
        name: str = "V2EX热门",
        url: str = "https://www.v2ex.com/index.xml",  # 热门话题页面
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "technology",
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
            "debug_mode": False,  # 是否保存调试文件
            "debug_file": "v2ex_debug_content.xml"  # 调试文件名称
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
        logger.info(f"Initialized {self.name} Selenium adapter with URL: {self.url}")
    
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
            
            # 记录driver进程ID，用于后续清理
            try:
                self._driver_pid = driver.service.process.pid
                logger.info(f"ChromeDriver process ID: {self._driver_pid}")
            except Exception as pid_e:
                logger.warning(f"Could not capture ChromeDriver PID: {str(pid_e)}")
                
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
        # 清理临时XML文件
        try:
            debug_file = self.config.get("debug_file", "v2ex_debug_content.xml")
            extracted_xml_file = "v2ex_extracted_xml.xml"
            
            # 清理debug_file
            if os.path.exists(debug_file):
                os.remove(debug_file)
                logger.debug(f"Removed temporary debug file: {debug_file}")
            
            # 清理extracted_xml_file
            if os.path.exists(extracted_xml_file):
                os.remove(extracted_xml_file)
                logger.debug(f"Removed temporary extracted XML file: {extracted_xml_file}")
        except Exception as e:
            logger.error(f"Error removing temporary XML files: {str(e)}")
        
        await self._close_driver()
        await super().close()
    
    async def _fetch_with_selenium(self) -> str:
        """
        使用Selenium从V2EX获取页面内容
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
            await loop.run_in_executor(None, lambda: driver.get(self.url))
            
            # 等待页面加载完成
            wait_time = self.config.get("selenium_wait_time", 5)
            
            # 如果是XML页面，等待pre元素（XML通常会在pre标签中显示）
            if self.config.get("parse_xml", False):
                try:
                    # 先等待body元素
                    await loop.run_in_executor(
                        None,
                        lambda: WebDriverWait(driver, wait_time).until(
                            EC.presence_of_element_located((By.TAG_NAME, "body"))
                        )
                    )
                    logger.debug("Body element loaded successfully")
                    
                    # 等待一段时间，确保页面完全加载
                    await asyncio.sleep(2)
                    
                    # 直接获取页面源代码，不再尝试查找pre元素
                    # 因为pre元素可能在页面源代码中，但不一定在DOM中
                    html_content = await loop.run_in_executor(None, lambda: driver.page_source)
                    logger.info(f"Successfully fetched page content with Selenium, content length: {len(html_content)}")
                    
                    # 随机滚动页面，模拟人类行为
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
                    
                    return html_content
                    
                except TimeoutException:
                    logger.warning(f"Timeout waiting for main content to load after {wait_time} seconds")
                    # 即使超时，也尝试获取页面源代码
                    html_content = await loop.run_in_executor(None, lambda: driver.page_source)
                    return html_content
            
            # 如果不是XML页面，等待主要内容元素
            else:
                try:
                    # 等待主要内容元素
                    await loop.run_in_executor(
                        None,
                        lambda: WebDriverWait(driver, wait_time).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".topic-link"))
                        )
                    )
                    logger.debug("Main content loaded successfully")
                except TimeoutException:
                    logger.warning(f"Timeout waiting for main content to load after {wait_time} seconds")
                
                # 获取页面源代码
                html_content = await loop.run_in_executor(None, lambda: driver.page_source)
                logger.info(f"Successfully fetched page content with Selenium, content length: {len(html_content)}")
                
                # 随机滚动页面，模拟人类行为
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
            
            return html_content
            
        except Exception as e:
            logger.error(f"Error fetching with Selenium: {str(e)}", exc_info=True)
            return ""
    
    def _unescape_content(self, content: str) -> str:
        """
        处理内容中的转义字符
        特别是处理Unicode转义序列，如\u003C（<）和\u003E（>）
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
        解析XML内容，提取话题信息
        适用于从 https://www.v2ex.com/index.xml 获取的数据
        XML内容可能直接来自pre标签
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
        解析HTML内容，提取话题信息
        适用于从热门话题页面获取的数据
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
        解析响应内容
        """
        try:
            # 检查响应是否为空
            if not response or not response.strip():
                logger.warning("Empty response received")
                return []
            
            # 检查内容类型
            is_xml = response.strip().startswith('<?xml') or response.strip().startswith('<rss')
            
            # 根据内容类型或配置决定解析方式
            if is_xml or self.config.get("parse_xml", False):
                logger.info("Content appears to be XML, using _parse_xml method")
                return await self._parse_xml(response)
            else:
                logger.info("Content appears to be HTML, using _parse_html method")
                return await self._parse_html(response)
        except Exception as e:
            logger.error(f"Error parsing response: {str(e)}")
            return []

    async def fetch(self) -> List[NewsItemModel]:
        """
        获取V2EX热门话题
        """
        try:
            # 现有代码
            result = await super().fetch()
            return result
        finally:
            # 确保每次fetch后都关闭driver，防止资源泄漏
            await self._close_driver() 