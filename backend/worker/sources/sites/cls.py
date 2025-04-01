import logging
import datetime
import os
from typing import List, Dict, Any, Optional, Union
import aiohttp
import json
import asyncio
import re
import random
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import time
import hashlib
import traceback
import requests

# 添加Selenium相关导入
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

from worker.sources.base import NewsItemModel
from worker.sources.rest_api import RESTNewsSource

logger = logging.getLogger(__name__)


class CLSNewsSource(RESTNewsSource):
    """
    财联社新闻源适配器
    使用多种方式获取财联社内容:
    1. 财联社电报（实时新闻）
    2. 热门文章排行榜
    3. 环球市场情报
    支持API访问和Selenium网页抓取两种方式
    """
    
    # 财联社官方URL
    CLS_BASE_URL = "https://www.cls.cn"
    CLS_TELEGRAPH_URL = "https://www.cls.cn/telegraph"
    CLS_GLOBAL_MARKET_URL = "https://www.cls.cn/subject/1556" # 环球市场情报
    CLS_HOT_ARTICLE_URL = "https://www.cls.cn/telegraph?type=hot" # 热门文章
    
    # 财联社API端点
    API_TELEGRAPH = "https://www.cls.cn/nodeapi/telegraphs"  # 电报API
    API_HOT_ARTICLE = "https://www.cls.cn/nodeapi/telegraphList"  # 热门文章API
    
    # 备用第三方API
    BACKUP_API_URLS = [
        "https://api.vvhan.com/api/hotlist/zxnew",  # 综合新闻
        "https://api.apiopen.top/api/getWangYiNews?page=1&count=30&type=finance",
        "https://api.oioweb.cn/api/news/financial",
        "https://api.mcloc.cn/finance"
    ]
    
    # 用户代理列表，模拟不同的浏览器
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
    ]
    
    # 初始化WebDriver为None，延迟加载
    _driver = None
    _driver_pid = None
    
    def __init__(
        self,
        source_id: str = "cls",
        name: str = "财联社",
        api_url: str = None,
        update_interval: int = 300,  # 5分钟
        cache_ttl: int = 180,  # 3分钟
        category: str = "finance",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        # 初始化日志记录器
        self.logger = logging.getLogger(__name__)
        
        # 确保配置是一个字典
        self.config = config if config else {}
        
        # 默认使用电报API
        if not api_url:
            api_url = self.API_TELEGRAPH
            
        # 初始化父类
        super().__init__(
            source_id=source_id,
            name=name,
            api_url=api_url,
            update_interval=update_interval,
            cache_ttl=cache_ttl,
            category=category,
            country=country,
            language=language
        )
        
        # 从配置中获取选项
        self.use_selenium = self.config.get("use_selenium", False)
        self.use_direct_api = self.config.get("use_direct_api", True)
        self.use_scraping = self.config.get("use_scraping", True)
        self.use_backup_api = self.config.get("use_backup_api", True)
        
        self.logger.info(f"初始化财联社适配器，配置: use_selenium={self.use_selenium}, "
                     f"use_direct_api={self.use_direct_api}, "
                     f"use_scraping={self.use_scraping}, "
                     f"use_backup_api={self.use_backup_api}")
        
        # WebDriver实例，需要时才初始化
        self._driver = None
        self._driver_pid = None
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        获取财联社新闻
        尝试多种途径获取财联社内容:
        1. 直接API获取
        2. 网页抓取
        3. 第三方API
        """
        # 初始化日志记录器
        logger = logging.getLogger(__name__)
        logger.info(f"开始获取财联社新闻，配置: use_selenium={self.use_selenium}, use_direct_api={self.use_direct_api}, use_scraping={self.use_scraping}, use_backup_api={self.use_backup_api}")
        
        news_items = []
        errors = []
        
        # 1. 尝试使用直接API获取
        if self.use_direct_api:
            try:
                logger.info("尝试使用财联社API获取新闻...")
                
                # 获取电报新闻
                try:
                    telegraph_items = await self._fetch_telegraph()
                    if telegraph_items:
                        logger.info(f"从API获取到 {len(telegraph_items)} 条财联社电报")
                        news_items.extend(telegraph_items)
                except Exception as e:
                    err_msg = f"从财联社电报API获取新闻失败: {str(e)}"
                    logger.error(err_msg)
                    errors.append(err_msg)
                
                # 获取热门文章
                try:
                    hot_items = await self._fetch_hot_articles()
                    if hot_items:
                        logger.info(f"从API获取到 {len(hot_items)} 条热门文章")
                        news_items.extend(hot_items)
                except Exception as e:
                    err_msg = f"从财联社热门文章API获取新闻失败: {str(e)}"
                    logger.error(err_msg)
                    errors.append(err_msg)
                
                # 获取环球市场情报
                try:
                    global_items = await self._fetch_global_market()
                    if global_items:
                        logger.info(f"从API获取到 {len(global_items)} 条环球市场情报")
                        news_items.extend(global_items)
                except Exception as e:
                    err_msg = f"从财联社环球市场情报API获取新闻失败: {str(e)}"
                    logger.error(err_msg)
                    errors.append(err_msg)
                
            except Exception as e:
                err_msg = f"使用财联社API获取新闻失败: {str(e)}"
                logger.error(err_msg)
                errors.append(err_msg)
        
        # 2. 如果API获取失败，尝试网页抓取
        if not news_items and self.use_scraping:
            try:
                logger.info("尝试使用网页抓取获取财联社新闻...")
                scrape_items = await self._scrape_cls_website()
                if scrape_items:
                    logger.info(f"通过网页抓取获取到 {len(scrape_items)} 条新闻")
                    news_items.extend(scrape_items)
            except Exception as e:
                err_msg = f"使用网页抓取获取财联社新闻失败: {str(e)}"
                logger.error(err_msg)
                errors.append(err_msg)
        
        # 3. 如果仍然没有获取到新闻，尝试使用备用API
        if not news_items and self.use_backup_api:
            logger.info("尝试使用备用API获取财联社新闻...")
            for api_url in self.BACKUP_API_URLS:
                try:
                    backup_items = await self._fetch_from_backup_api(api_url)
                    if backup_items:
                        logger.info(f"从备用API {api_url} 获取到 {len(backup_items)} 条新闻")
                        news_items.extend(backup_items)
                        break  # 一旦成功获取，就不再尝试其他备用API
                except Exception as e:
                    err_msg = f"从备用API {api_url} 获取新闻失败: {str(e)}"
                    logger.error(err_msg)
                    errors.append(err_msg)
        
        # 4. 如果还是没有获取到新闻，抛出异常
        if not news_items:
            error_message = "无法从财联社获取新闻，所有尝试均失败: " + "; ".join(errors)
            logger.error(error_message)
            raise RuntimeError(error_message)
        
        # 对新闻项进行去重
        unique_news = {}
        for item in news_items:
            if item.id not in unique_news:
                unique_news[item.id] = item
        
        result = list(unique_news.values())
        logger.info(f"成功获取到 {len(result)} 条财联社新闻")
        return result
    
    async def _fetch_telegraph(self) -> List[NewsItemModel]:
        """获取财联社电报内容"""
        try:
            url = self.API_TELEGRAPH
            params = {
                "app": "CailianpressWeb",
                "os": "web",
                "sv": "8.4.6",
                "category": "",
                "rn": 20,
                "lastTime": int(datetime.datetime.now().timestamp() * 1000),
                "last_time": int(datetime.datetime.now().timestamp() * 1000),
                "subscribe": 0
            }
            
            # 为API请求设置特殊headers
            api_headers = self.headers.copy()
            api_headers.update({
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "x-app-id": "CailianpressWeb",
                "x-os": "web",
                "x-sv": "8.4.6"
            })
            
            # 随机延迟，模拟人类行为
            await asyncio.sleep(0.5 + random.random())
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=api_headers, timeout=10) as response:
                    if response.status != 200:
                        logger.warning(f"获取财联社电报失败，状态码: {response.status}")
                        return []
                    
                    data = await response.json()
                    
                    if not data or "data" not in data or "roll_data" not in data["data"]:
                        logger.warning("获取财联社电报数据格式不正确")
                        return []
                    
                    telegraph_list = data["data"]["roll_data"]
                    
                    news_items = []
                    for item in telegraph_list:
                        try:
                            article_id = item.get("article_id")
                            title = item.get("title")
                            if not title or not article_id:
                                continue
                            
                            # 构建完整URL
                            url = f"https://www.cls.cn/detail/{article_id}"
                            
                            # 发布时间
                            ctime = item.get("ctime")
                            published_at = None
                            if ctime:
                                try:
                                    published_at = datetime.datetime.fromtimestamp(ctime)
                                except:
                                    pass
                            
                            # 图片
                            image_url = None
                            images = item.get("images", [])
                            if images and len(images) > 0:
                                image_url = images[0]
                            elif item.get("img"):
                                image_url = item.get("img")
                            
                            # 摘要
                            summary = item.get("brief", "")
                            
                            # 创建新闻项
                            news_item = self.create_news_item(
                                id=f"cls-{article_id}",
                                title=title,
                                url=url,
                                content=summary,
                                summary=summary,
                                image_url=image_url,
                                published_at=published_at,
                                extra={
                                    "source": "财联社电报",
                                    "article_id": article_id,
                                    "source_id": self.source_id,
                                    "reading_num": item.get("reading_num"),
                                    "comment_num": item.get("comment_num"),
                                    "share_num": item.get("share_num")
                                }
                            )
                            
                            news_items.append(news_item)
                        except Exception as e:
                            logger.warning(f"处理财联社电报项目失败: {str(e)}")
                    
                    logger.info(f"成功解析 {len(news_items)} 条财联社电报")
                    return news_items
        except Exception as e:
            logger.error(f"获取财联社电报失败: {str(e)}")
            raise RuntimeError(f"获取财联社电报失败: {str(e)}")
    
    async def _fetch_hot_articles(self) -> List[NewsItemModel]:
        """获取财联社热门文章"""
        try:
            url = self.API_HOT_ARTICLE
            params = {
                "app": "CailianpressWeb",
                "os": "web",
                "sv": "8.4.6",
                "type": "hot",
                "page": 1,
                "rn": 10
            }
            
            # 为API请求设置特殊headers
            api_headers = self.headers.copy()
            api_headers.update({
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "x-app-id": "CailianpressWeb",
                "x-os": "web",
                "x-sv": "8.4.6"
            })
            
            # 随机延迟，模拟人类行为
            await asyncio.sleep(0.5 + random.random())
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=api_headers, timeout=10) as response:
                    if response.status != 200:
                        logger.warning(f"获取财联社热门文章失败，状态码: {response.status}")
                        return []
                    
                    data = await response.json()
                    
                    if not data or "data" not in data or "telegraph_list" not in data["data"]:
                        logger.warning("获取财联社热门文章数据格式不正确")
                        return []
                    
                    article_list = data["data"]["telegraph_list"]
                    
                    news_items = []
                    for item in article_list:
                        try:
                            article_id = item.get("id")
                            title = item.get("title")
                            if not title or not article_id:
                                continue
                            
                            # 构建完整URL
                            url = f"https://www.cls.cn/detail/{article_id}"
                            
                            # 发布时间
                            time = item.get("time")
                            published_at = None
                            if time:
                                try:
                                    published_at = datetime.datetime.fromtimestamp(time / 1000)
                                except:
                                    pass
                            
                            # 图片
                            image_url = item.get("thumbnails", [None])[0]
                            
                            # 摘要
                            summary = item.get("brief", "")
                            
                            # 创建新闻项
                            news_item = self.create_news_item(
                                id=f"cls-hot-{article_id}",
                                title=title,
                                url=url,
                                content=summary,
                                summary=summary,
                                image_url=image_url,
                                published_at=published_at,
                                extra={
                                    "source": "财联社热门文章",
                                    "article_id": article_id,
                                    "source_id": self.source_id,
                                    "view_count": item.get("view_count"),
                                    "share_count": item.get("share_count")
                                }
                            )
                            
                            news_items.append(news_item)
                        except Exception as e:
                            logger.warning(f"处理财联社热门文章失败: {str(e)}")
                    
                    logger.info(f"成功解析 {len(news_items)} 条财联社热门文章")
                    return news_items
        except Exception as e:
            logger.error(f"获取财联社热门文章失败: {str(e)}")
            raise RuntimeError(f"获取财联社热门文章失败: {str(e)}")
    
    async def _fetch_global_market(self) -> List[NewsItemModel]:
        """获取环球市场情报"""
        try:
            url = f"https://www.cls.cn/nodeapi/telegraphList"
            params = {
                "app": "CailianpressWeb",
                "os": "web",
                "sv": "8.4.6",
                "subject_id": "1556",  # 环球市场情报的ID
                "page": 1,
                "rn": 10
            }
            
            # 为API请求设置特殊headers
            api_headers = self.headers.copy()
            api_headers.update({
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "x-app-id": "CailianpressWeb",
                "x-os": "web",
                "x-sv": "8.4.6"
            })
            
            # 随机延迟，模拟人类行为
            await asyncio.sleep(0.5 + random.random())
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=api_headers, timeout=10) as response:
                    if response.status != 200:
                        logger.warning(f"获取环球市场情报失败，状态码: {response.status}")
                        return []
                    
                    data = await response.json()
                    
                    if not data or "data" not in data or "telegraph_list" not in data["data"]:
                        logger.warning("获取环球市场情报数据格式不正确")
                        return []
                    
                    article_list = data["data"]["telegraph_list"]
                    
                    news_items = []
                    for item in article_list:
                        try:
                            article_id = item.get("id")
                            title = item.get("title")
                            if not title or not article_id:
                                continue
                            
                            # 构建完整URL
                            url = f"https://www.cls.cn/detail/{article_id}"
                            
                            # 发布时间
                            time = item.get("time")
                            published_at = None
                            if time:
                                try:
                                    published_at = datetime.datetime.fromtimestamp(time / 1000)
                                except:
                                    pass
                            
                            # 图片
                            image_url = item.get("thumbnails", [None])[0]
                            
                            # 摘要
                            summary = item.get("brief", "")
                            
                            # 创建新闻项
                            news_item = self.create_news_item(
                                id=f"cls-global-{article_id}",
                                title=title,
                                url=url,
                                content=summary,
                                summary=summary,
                                image_url=image_url,
                                published_at=published_at,
                                extra={
                                    "source": "环球市场情报",
                                    "article_id": article_id,
                                    "source_id": self.source_id,
                                    "view_count": item.get("view_count"),
                                    "share_count": item.get("share_count")
                                }
                            )
                            
                            news_items.append(news_item)
                        except Exception as e:
                            logger.warning(f"处理环球市场情报项目失败: {str(e)}")
                    
                    logger.info(f"成功解析 {len(news_items)} 条环球市场情报")
                    return news_items
        except Exception as e:
            logger.error(f"获取环球市场情报失败: {str(e)}")
            raise RuntimeError(f"获取环球市场情报失败: {str(e)}")
    
    async def _scrape_cls_website(self) -> List[NewsItemModel]:
        """
        使用HTTP请求抓取财联社网站
        根据配置决定使用哪种方式抓取
        """
        # 初始化日志记录器
        logger = logging.getLogger(__name__)
        
        try:
            news_items = []
            
            # 如果禁用了Selenium或者Selenium不可用时使用HTTP请求
            if not self.use_selenium:
                logger.info("抓取财联社网站 - 使用HTTP请求")
                
                # 1. 抓取电报页面
                try:
                    telegraph_items = await self._scrape_telegraph_page()
                    if telegraph_items:
                        logger.info(f"从电报页面获取到 {len(telegraph_items)} 条新闻")
                        news_items.extend(telegraph_items)
                except Exception as e:
                    logger.error(f"抓取电报页面出错: {str(e)}")
                
                # 2. 抓取热门文章
                try:
                    hot_items = await self._fetch_global_market()
                    if hot_items:
                        logger.info(f"从环球市场情报页面获取到 {len(hot_items)} 条新闻")
                        news_items.extend(hot_items)
                except Exception as e:
                    logger.error(f"抓取环球市场情报页面出错: {str(e)}")
                
                return news_items
            
            # 否则使用Selenium
            logger.info("抓取财联社网站 - 使用Selenium")
            
            # 1. 抓取电报页面
            try:
                telegraph_items = await self._scrape_with_selenium(self.CLS_TELEGRAPH_URL, "telegraph")
                if telegraph_items:
                    logger.info(f"使用Selenium从电报页面获取到 {len(telegraph_items)} 条新闻")
                    news_items.extend(telegraph_items)
            except Exception as e:
                logger.error(f"使用Selenium抓取电报页面出错: {str(e)}")
            
            # 2. 抓取热门文章
            try:
                hot_items = await self._scrape_with_selenium(self.CLS_HOT_ARTICLE_URL, "hot")
                if hot_items:
                    logger.info(f"使用Selenium从热门文章页面获取到 {len(hot_items)} 条新闻")
                    news_items.extend(hot_items)
            except Exception as e:
                logger.error(f"使用Selenium抓取热门文章页面出错: {str(e)}")
            
            # 3. 抓取环球市场情报
            try:
                global_items = await self._scrape_with_selenium(self.CLS_GLOBAL_MARKET_URL, "global")
                if global_items:
                    logger.info(f"使用Selenium从环球市场情报页面获取到 {len(global_items)} 条新闻")
                    news_items.extend(global_items)
            except Exception as e:
                logger.error(f"使用Selenium抓取环球市场情报页面出错: {str(e)}")
            
            return news_items
        except Exception as e:
            logger.error(f"抓取财联社网站时发生未知错误: {str(e)}")
            return []
    
    async def _scrape_with_selenium(self, url: str, page_type: str) -> List[NewsItemModel]:
        """
        使用Selenium抓取页面内容
        
        Args:
            url: 要抓取的URL
            page_type: 页面类型，如telegraph, hot, global
            
        Returns:
            List[NewsItemModel]: 新闻项列表
        """
        logger.info(f"使用Selenium抓取 {url}")
        
        # 检查是否已经创建了driver
        driver = None
        try:
            driver = await self._get_driver()
            if driver is None:
                logger.error("无法创建WebDriver实例")
                raise RuntimeError("无法抓取数据：WebDriver创建失败")
            
            news_items = []
            
            # 随机延迟，模拟人类行为
            if self.config.get("use_random_delay", True):
                delay = random.uniform(
                    self.config.get("min_delay", 1.0),
                    self.config.get("max_delay", 3.0)
                )
                logger.debug(f"随机延迟 {delay:.2f} 秒")
                await asyncio.sleep(delay)
            
            # 访问页面
            try:
                logger.info(f"访问URL: {url}")
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: driver.get(url))
                
                # 等待页面加载
                wait_time = self.config.get("selenium_wait_time", 5)
                
                try:
                    # 等待页面主要内容加载完成
                    # 不同页面可能有不同的选择器
                    if page_type == "telegraph":
                        selector = ".detail-telegraph-content, .telegraph-item, .telegraph-list, .roll-item"
                    elif page_type == "hot":
                        selector = ".detail-hot-article-content, .hot-article-item, .hot-article-list"
                    elif page_type == "global":
                        selector = ".detail-market-content, .market-item, .market-list"
                    else:
                        selector = ".container, .content"
                    
                    # 使用显式等待
                    wait = WebDriverWait(driver, wait_time)
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    
                    # 页面已加载，执行额外操作
                    # 1. 向下滚动以加载更多内容
                    scroll_count = 3  # 滚动次数
                    for _ in range(scroll_count):
                        await loop.run_in_executor(None, lambda: driver.execute_script("window.scrollBy(0, 500);"))
                        await asyncio.sleep(0.5)  # 等待内容加载
                except TimeoutException:
                    logger.warning(f"等待元素 {selector} 超时，继续处理已加载内容")
                
                # 尝试两种方法获取内容：
                # 1. 从页面中提取嵌入的JSON数据
                # 2. 如果无法获取JSON，则直接解析DOM
                
                # 获取页面HTML
                html = await loop.run_in_executor(None, lambda: driver.page_source)
                
                # 尝试从HTML中提取JSON数据
                soup = BeautifulSoup(html, 'html.parser')
                
                # 方法1: 寻找包含数据的script标签
                for script in soup.find_all('script'):
                    script_text = script.string
                    if not script_text:
                        continue
                    
                    # 查找可能包含数据的JSON
                    json_patterns = [
                        r'window.__INITIAL_STATE__\s*=\s*({.*?});',
                        r'telegraph_list":\s*(\[.*?\])',
                        r'REDUX_STATE\s*=\s*({.*?});\s*</script>'
                    ]
                    
                    for pattern in json_patterns:
                        try:
                            match = re.search(pattern, script_text, re.DOTALL)
                            if match:
                                json_str = match.group(1)
                                data = json.loads(json_str)
                                
                                # 根据页面类型提取不同的数据
                                if page_type == "telegraph":
                                    items_key = "telegraph_list"
                                elif page_type == "hot":
                                    items_key = "hot_list"
                                elif page_type == "global":
                                    items_key = "subject_list"
                                else:
                                    items_key = "list"
                                
                                # 尝试从不同的路径提取数据
                                items = None
                                
                                # 尝试直接获取
                                if items_key in data:
                                    items = data[items_key]
                                # 尝试从data字段获取
                                elif "data" in data and items_key in data["data"]:
                                    items = data["data"][items_key]
                                # 尝试从result字段获取
                                elif "result" in data and items_key in data["result"]:
                                    items = data["result"][items_key]
                                
                                if items and isinstance(items, list):
                                    for item in items:
                                        try:
                                            article_id = item.get("id") or item.get("article_id")
                                            title = item.get("title")
                                            if not title or not article_id:
                                                continue
                                            
                                            url = f"https://www.cls.cn/detail/{article_id}"
                                            summary = item.get("brief", "") or item.get("summary", "")
                                            
                                            # 发布时间
                                            pub_time = item.get("time") or item.get("ctime")
                                            published_at = None
                                            if pub_time:
                                                try:
                                                    # 尝试解析时间戳（毫秒或秒）
                                                    if pub_time > 1000000000000:  # 如果是毫秒时间戳
                                                        published_at = datetime.datetime.fromtimestamp(pub_time / 1000)
                                                    else:  # 如果是秒时间戳
                                                        published_at = datetime.datetime.fromtimestamp(pub_time)
                                                except:
                                                    pass
                                            
                                            # 图片
                                            image_url = None
                                            if "images" in item and item["images"] and len(item["images"]) > 0:
                                                image_url = item["images"][0]
                                            elif "thumbnails" in item and item["thumbnails"] and len(item["thumbnails"]) > 0:
                                                image_url = item["thumbnails"][0]
                                            elif "img" in item:
                                                image_url = item["img"]
                                            
                                            # 创建新闻项
                                            source_type = {
                                                "telegraph": "财联社电报(JSON)",
                                                "hot": "财联社热门(JSON)",
                                                "global": "环球市场情报(JSON)"
                                            }.get(page_type, "财联社(JSON)")
                                            
                                            news_item = self.create_news_item(
                                                id=f"cls-json-{page_type}-{article_id}",
                                                title=title,
                                                url=url,
                                                content=summary,
                                                summary=summary,
                                                image_url=image_url,
                                                published_at=published_at,
                                                extra={
                                                    "source": source_type,
                                                    "article_id": article_id,
                                                    "source_id": self.source_id,
                                                    "view_count": item.get("view_count"),
                                                    "share_count": item.get("share_count")
                                                }
                                            )
                                            
                                            news_items.append(news_item)
                                        except Exception as e:
                                            logger.warning(f"处理JSON中的新闻项失败: {str(e)}")
                                    
                                    if news_items:
                                        logger.info(f"成功从JSON中提取 {len(news_items)} 条新闻")
                                        break
                        except Exception as e:
                            logger.warning(f"解析JSON数据失败: {str(e)}")
                
                # 方法2: 如果没有从JSON提取到数据，直接解析DOM
                if not news_items:
                    # 不同页面类型的选择器列表
                    selectors = []
                    if page_type == "telegraph":
                        selectors = [
                            ".cls-telegraph-list .telegraph-item",
                            ".roll-list .roll-item",
                            ".telegraph-list li"
                        ]
                    elif page_type == "hot":
                        selectors = [
                            ".hot-list .hot-item",
                            ".hot-article-list li"
                        ]
                    elif page_type == "global":
                        selectors = [
                            ".market-list .market-item",
                            ".subject-list li"
                        ]
                    
                    # 尝试每个选择器
                    for selector in selectors:
                        article_elements = soup.select(selector)
                        for index, elem in enumerate(article_elements):
                            try:
                                # 提取链接和标题
                                link_elem = elem.select_one("a")
                                if not link_elem:
                                    continue
                                
                                link = link_elem.get("href", "")
                                if not link.startswith("http"):
                                    link = urljoin(self.CLS_BASE_URL, link)
                                
                                # 提取文章ID
                                article_id = None
                                id_match = re.search(r'/detail/(\d+)', link)
                                if id_match:
                                    article_id = id_match.group(1)
                                else:
                                    article_id = f"dom-{hash(link) % 100000000}"
                                
                                # 提取标题
                                title_elem = elem.select_one(".title, .item-title, h3, h4")
                                title = title_elem.text.strip() if title_elem else link_elem.text.strip()
                                
                                # 提取摘要
                                summary_elem = elem.select_one(".desc, .brief, .summary, p")
                                summary = summary_elem.text.strip() if summary_elem else ""
                                
                                # 提取图片
                                image_url = None
                                img_elem = elem.select_one("img")
                                if img_elem and img_elem.has_attr("src"):
                                    image_url = img_elem["src"]
                                    if not image_url.startswith(("http://", "https://")):
                                        image_url = urljoin(self.CLS_BASE_URL, image_url)
                                
                                # 创建新闻项
                                source_type = {
                                    "telegraph": "财联社电报(DOM)",
                                    "hot": "财联社热门(DOM)",
                                    "global": "环球市场情报(DOM)"
                                }.get(page_type, "财联社(DOM)")
                                
                                news_item = self.create_news_item(
                                    id=f"cls-dom-{page_type}-{article_id}",
                                    title=title,
                                    url=link,
                                    content=summary,
                                    summary=summary,
                                    image_url=image_url,
                                    published_at=datetime.datetime.now(),
                                    extra={
                                        "source": source_type,
                                        "article_id": article_id,
                                        "source_id": self.source_id,
                                        "rank": index + 1
                                    }
                                )
                                
                                news_items.append(news_item)
                            except Exception as e:
                                logger.warning(f"处理DOM中的新闻项失败: {str(e)}")
                        
                        # 如果找到了新闻项，中断选择器循环
                        if news_items:
                            break
                
                logger.info(f"成功从 {url} 抓取到 {len(news_items)} 条新闻")
                return news_items
            except WebDriverException as wde:
                logger.error(f"WebDriver错误: {str(wde)}")
                raise RuntimeError(f"WebDriver发生错误: {str(wde)}")
            except Exception as e:
                logger.error(f"使用Selenium抓取页面失败: {str(e)}")
                raise RuntimeError(f"使用Selenium抓取页面失败: {str(e)}")
        except Exception as e:
            logger.error(f"Selenium抓取过程中发生错误: {str(e)}", exc_info=True)
            # 不在这里关闭driver，让外部调用者处理异常并关闭
            raise
        finally:
            # 不要在这里关闭WebDriver，因为同一实例可能会被复用
            pass
    
    async def _scrape_telegraph_page(self):
        """Scrape CLS telegraph page using HTTP"""
        logger = logging.getLogger(__name__)
        logger.info("Scraping telegraph page")
        session = requests.Session()
        
        # 明确使用桌面版用户代理，避免重定向到移动版
        desktop_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
        
        session.headers.update({
            "User-Agent": desktop_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
        })
        # 电报页面
        telegraph_url = "https://www.cls.cn/telegraph"

        try:
            response = session.get(telegraph_url, timeout=10, verify=True)
            logger.info(f"Got response with status code: {response.status_code}")
            
            # 记录内容长度但不再保存HTML文件
            logger.info(f"Received HTML content, length: {len(response.text)}")
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找电报列表容器
            result = []
            
            # 检查是否存在PC版的电报列表
            telegraph_list = soup.find(class_="home-telegraph-list")
            
            if telegraph_list:
                logger.info("Found PC version home-telegraph-list container")
                # 获取所有电报项
                telegraph_items = telegraph_list.find_all(class_="home-telegraph-item")
                logger.info(f"Found {len(telegraph_items)} telegraph items")
                
                for item in telegraph_items:
                    try:
                        # 获取链接和文本
                        link_element = item.find('a')
                        if not link_element:
                            continue
                        
                        # 获取链接URL
                        href = link_element.get('href', '')
                        url = f"https://www.cls.cn{href}" if href.startswith('/') else href
                        
                        # 获取时间
                        time_span = link_element.find('span')
                        time_text = time_span.text.strip() if time_span else ""
                        
                        # 获取标题/内容
                        content = link_element.text.strip()
                        if time_text:
                            content = content.replace(time_text, '', 1).strip()
                        
                        # 处理时间
                        today = datetime.datetime.now().strftime("%Y-%m-%d")
                        pub_time = int(time.time())
                        
                        if time_text:
                            try:
                                # 创建时间戳
                                time_parts = time_text.strip().split(':')
                                hour = int(time_parts[0])
                                minute = int(time_parts[1])
                                
                                dt = datetime.datetime.now().replace(
                                    hour=hour, minute=minute, second=0, microsecond=0
                                )
                                pub_time = int(dt.timestamp())
                            except Exception as e:
                                logger.warning(f"Failed to parse time: {time_text}: {e}")
                        
                        # 从内容中提取标题（如果有的话）
                        title = ""
                        if '【' in content and '】' in content:
                            title_match = re.search(r'【(.+?)】', content)
                            if title_match:
                                title = f"【{title_match.group(1)}】"
                        
                        if not title:
                            title = content[:30] + ('...' if len(content) > 30 else '')
                        
                        # 创建新闻项
                        news_item = NewsItemModel(
                            id=f"cls_telegraph_{hashlib.md5(content.encode()).hexdigest()}",
                            title=title,
                            content=content,
                            url=url,
                            source_id=self.source_id,
                            source_name=self.name,
                            published_at=datetime.datetime.fromtimestamp(pub_time),
                            category=self.category,
                            language=self.language,
                            country=self.country,
                            extra={
                                "source": "财联社电报",
                                "fetched_by": "web_scraping"
                            }
                        )
                        
                        result.append(news_item)
                    except Exception as e:
                        logger.warning(f"Error parsing telegraph item: {e}")
                
                logger.info(f"Successfully parsed {len(result)} items from home-telegraph-list")
                return result
            
            # 检查是否为移动版页面，尝试从移动版结构中提取内容
            logger.info("Checking for mobile version structure")
            
            # 移动版可能的结构：电报列表项目可能有不同的类名
            mobile_items = []
            
            # 尝试各种可能的移动版电报项类名
            for class_name in ["telegraph-item", "cls-telegraph-item", "mobile-telegraph-item", "feed-item", "feed-telegraph"]:
                items = soup.find_all(class_=class_name)
                if items:
                    logger.info(f"Found {len(items)} items with class '{class_name}'")
                    mobile_items.extend(items)
            
            # 如果找到了移动版电报项
            if mobile_items:
                logger.info(f"Found {len(mobile_items)} mobile telegraph items in total")
                
                for item in mobile_items:
                    try:
                        # 尝试提取链接
                        link_element = item.find('a')
                        if not link_element:
                            # 如果没有直接的链接元素，item本身可能是链接
                            if item.name == 'a':
                                link_element = item
                            else:
                                continue
                        
                        # 获取链接URL
                        href = link_element.get('href', '')
                        url = f"https://www.cls.cn{href}" if href.startswith('/') else href
                        if not url.startswith('http'):
                            url = f"https://www.cls.cn{url}" if url.startswith('/') else f"https://www.cls.cn/{url}"
                        
                        # 获取时间 - 移动版可能在不同的元素中
                        time_text = ""
                        time_element = item.find(class_=lambda c: c and ('time' in c.lower() or 'date' in c.lower()))
                        if time_element:
                            time_text = time_element.text.strip()
                        
                        # 获取内容 - 可能在不同的元素中
                        content_element = item.find(class_=lambda c: c and ('content' in c.lower() or 'text' in c.lower() or 'title' in c.lower()))
                        content = content_element.text.strip() if content_element else item.text.strip()
                        
                        # 去除时间文本
                        if time_text and time_text in content:
                            content = content.replace(time_text, '', 1).strip()
                        
                        # 处理时间
                        pub_time = int(time.time())
                        if time_text:
                            try:
                                # 尝试不同的时间格式
                                if ':' in time_text:
                                    # 格式可能是 "HH:MM" 或 "MM-DD HH:MM"
                                    if '-' in time_text:
                                        # 格式如 "MM-DD HH:MM"
                                        date_parts = time_text.split(' ')[0].split('-')
                                        time_parts = time_text.split(' ')[1].split(':')
                                        month = int(date_parts[0])
                                        day = int(date_parts[1])
                                        hour = int(time_parts[0])
                                        minute = int(time_parts[1])
                                        
                                        now = datetime.datetime.now()
                                        dt = now.replace(month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
                                    else:
                                        # 格式如 "HH:MM"
                                        time_parts = time_text.split(':')
                                        hour = int(time_parts[0])
                                        minute = int(time_parts[1])
                                        
                                        dt = datetime.datetime.now().replace(
                                            hour=hour, minute=minute, second=0, microsecond=0
                                        )
                                    pub_time = int(dt.timestamp())
                            except Exception as e:
                                logger.warning(f"Failed to parse mobile time: {time_text}: {e}")
                        
                        # 从内容中提取标题（如果有的话）
                        title = ""
                        if '【' in content and '】' in content:
                            title_match = re.search(r'【(.+?)】', content)
                            if title_match:
                                title = f"【{title_match.group(1)}】"
                        
                        if not title:
                            title = content[:30] + ('...' if len(content) > 30 else '')
                        
                        # 创建新闻项
                        news_item = NewsItemModel(
                            id=f"cls_telegraph_mobile_{hashlib.md5(content.encode()).hexdigest()}",
                            title=title,
                            content=content,
                            url=url,
                            source_id=self.source_id,
                            source_name=self.name,
                            published_at=datetime.datetime.fromtimestamp(pub_time),
                            category=self.category,
                            language=self.language,
                            country=self.country,
                            extra={
                                "source": "财联社电报(移动版)",
                                "fetched_by": "web_scraping_mobile"
                            }
                        )
                        
                        result.append(news_item)
                    except Exception as e:
                        logger.warning(f"Error parsing mobile telegraph item: {e}")
                
                logger.info(f"Successfully parsed {len(result)} items from mobile version")
                if result:
                    return result
            
            # 如果找不到电报列表，尝试提取JSON数据
            logger.warning("Could not find telegraph list in PC or mobile version, trying to extract from JSON data")
            
            # 尝试从JSON中提取数据
            try:
                # 尝试查找包含JSON数据的脚本标签
                scripts = soup.find_all('script')
                for script in scripts:
                    script_text = script.string
                    if not script_text:
                        continue
                    
                    # 尝试提取JSON数据
                    json_patterns = [
                        r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
                        r'window\.__REDUX_STATE__\s*=\s*({.*?});',
                        r'"telegraphList":\s*(\[.*?\])',
                        r'"telegraph":\s*({.*?}),'
                    ]
                    
                    for pattern in json_patterns:
                        try:
                            matches = re.search(pattern, script_text, re.DOTALL)
                            if matches:
                                json_str = matches.group(1)
                                try:
                                    json_data = json.loads(json_str)
                                    logger.info("Found JSON data in script tag")
                                    
                                    # 从JSON数据中提取新闻项
                                    if isinstance(json_data, list):
                                        # 直接是新闻项列表
                                        items_data = json_data
                                    elif isinstance(json_data, dict):
                                        # 尝试在字典中查找新闻项列表
                                        if 'telegraphList' in json_data:
                                            items_data = json_data['telegraphList']
                                        elif 'telegraph' in json_data and 'telegraphList' in json_data['telegraph']:
                                            items_data = json_data['telegraph']['telegraphList']
                                        else:
                                            # 遍历所有可能包含新闻项的字段
                                            items_data = None
                                            for key, value in json_data.items():
                                                if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                                                    if 'title' in value[0] or 'content' in value[0]:
                                                        items_data = value
                                                        break
                                    else:
                                        # 不是有效的JSON数据结构
                                        continue
                                    
                                    if items_data and isinstance(items_data, list):
                                        for item in items_data:
                                            try:
                                                # 提取所需字段
                                                title = item.get('title', '')
                                                content = item.get('content', '')
                                                
                                                if not title and not content:
                                                    continue
                                                
                                                # 如果没有标题，使用内容的前部分
                                                if not title:
                                                    title = content[:30] + ('...' if len(content) > 30 else '')
                                                
                                                # 获取时间戳
                                                ctime = item.get('ctime', time.time())
                                                if isinstance(ctime, str):
                                                    try:
                                                        ctime = int(ctime)
                                                    except:
                                                        ctime = time.time()
                                                
                                                # 获取URL
                                                item_id = item.get('id', '')
                                                url = item.get('shareurl', '') or f"https://www.cls.cn/detail/{item_id}"
                                                
                                                # 创建新闻项
                                                news_item = NewsItemModel(
                                                    id=f"cls_telegraph_json_{item_id or hashlib.md5((title + content).encode()).hexdigest()}",
                                                    title=title,
                                                    content=content,
                                                    url=url,
                                                    source_id=self.source_id,
                                                    source_name=self.name,
                                                    published_at=datetime.datetime.fromtimestamp(ctime),
                                                    category=self.category,
                                                    language=self.language,
                                                    country=self.country,
                                                    extra={
                                                        "source": "财联社电报",
                                                        "fetched_by": "json_data"
                                                    }
                                                )
                                                
                                                result.append(news_item)
                                            except Exception as e:
                                                logger.warning(f"Error processing JSON item: {e}")
                                        
                                    logger.info(f"Extracted {len(result)} items from JSON data")
                                    if result:
                                        return result
                                except json.JSONDecodeError:
                                    logger.warning(f"Failed to parse JSON: {json_str[:100]}...")
                        except Exception as e:
                            logger.warning(f"Error processing script: {e}")
            except Exception as e:
                logger.warning(f"Error extracting JSON data: {e}")
            
            # 如果以上方法都失败，尝试直接正则提取
            if not result:
                logger.warning("Trying direct regex extraction")
                try:
                    # 直接使用正则表达式搜索内容
                    pattern = re.compile(r'"content":"(.*?)","in_roll"', re.DOTALL)
                    matches = pattern.findall(response.text)
                    
                    for match in matches:
                        content = match.replace('\\n', '\n').replace('\\"', '"')
                        news_item = NewsItemModel(
                            id=f"cls_telegraph_regex_{hashlib.md5(content.encode()).hexdigest()}",
                            title=content[:50],  # 使用内容的前50个字符作为标题
                            content=content,
                            url=telegraph_url,
                            source_id=self.source_id,
                            source_name=self.name,
                            published_at=datetime.datetime.now(),
                            category=self.category,
                            language=self.language,
                            country=self.country,
                            extra={
                                "source": "财联社电报",
                                "fetched_by": "regex"
                            }
                        )
                        result.append(news_item)
                    
                    logger.info(f"Extracted {len(result)} items with regex")
                except Exception as e:
                    logger.warning(f"Error in regex extraction: {e}")
            
            if not result:
                logger.warning("Could not extract any news items from the telegraph page")
            
            return result
        except Exception as e:
            logger.error(f"Error when scraping telegraph page: {e}")
            logger.exception(e)
            raise
    
    def _create_mock_data(self) -> List[NewsItemModel]:
        """
        不再生成模拟财经新闻数据，而是抛出异常
        """
        logger.error("请求获取财联社数据失败且无法回退到备用方法")
        raise RuntimeError("无法获取财联社新闻数据：所有获取方法均已失败")

    def _create_driver(self):
        """
        创建Chrome WebDriver实例
        
        Returns:
            WebDriver: Chrome WebDriver实例
        """
        try:
            logger.info("开始创建Chrome WebDriver")
            
            # 设置Chrome选项
            options = Options()
            
            # 无头模式
            options.add_argument("--headless")
            
            # 添加稳定性相关的参数
            options.add_argument("--no-sandbox")  # 禁用沙箱
            options.add_argument("--disable-dev-shm-usage")  # 禁用/dev/shm
            options.add_argument("--disable-gpu")  # 禁用GPU加速
            options.add_argument("--disable-extensions")  # 禁用扩展
            options.add_argument("--disable-setuid-sandbox")  # 禁用setuid沙箱
            options.add_argument("--disable-infobars")  # 禁用信息栏
            options.add_argument("--disable-notifications")  # 禁用通知
            options.add_argument("--disable-popup-blocking")  # 禁用弹窗拦截
            options.add_argument("--disable-software-rasterizer")  # 禁用软件光栅化器
            
            # 绕过自动化检测
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-features=site-per-process")
            options.add_argument("--disable-features=RendererCodeIntegrity")
            options.add_argument("--disable-features=AutomationMetadata")
            
            # 禁用默认的自动化扩展和控制器
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            options.add_experimental_option("excludeSwitches", ["enable-logging"])
            
            # 添加空扩展以绕过一些检测
            options.add_extension = []
            
            # 添加随机用户代理
            user_agent = random.choice(self.USER_AGENTS)
            options.add_argument(f"--user-agent={user_agent}")
            logger.debug(f"使用用户代理: {user_agent}")
            
            # 设置默认语言
            options.add_argument("--lang=zh-CN")
            
            # 使用指定的Chrome可执行文件（如果提供）
            chrome_executable = self.config.get("chrome_executable")
            if chrome_executable and os.path.exists(chrome_executable):
                logger.info(f"使用指定的Chrome可执行文件: {chrome_executable}")
                options.binary_location = chrome_executable
            
            # 创建服务
            try:
                chrome_service = Service(ChromeDriverManager().install())
            except Exception as e:
                logger.warning(f"使用ChromeDriverManager安装失败: {str(e)}")
                # 尝试直接使用系统ChromeDriver
                chrome_service = Service()
            
            # 设置超时
            timeout = self.config.get("selenium_timeout", 30)
            
            # 创建并返回WebDriver
            driver = webdriver.Chrome(service=chrome_service, options=options)
            
            # 设置页面加载超时
            driver.set_page_load_timeout(timeout)
            
            # 设置脚本执行超时
            driver.set_script_timeout(timeout)
            
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
        支持重试机制，确保更高的可靠性
        
        Returns:
            WebDriver: Chrome WebDriver实例，失败返回None
        """
        if self._driver is None:
            logger.info("WebDriver不存在，开始创建新的WebDriver实例")
            
            # 设置重试次数
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    # 在事件循环中运行阻塞的WebDriver创建
                    loop = asyncio.get_event_loop()
                    self._driver = await loop.run_in_executor(None, self._create_driver)
                    
                    if self._driver:
                        logger.info("成功创建并获取WebDriver实例")
                        # 使用一个简单的请求来测试WebDriver是否正常工作
                        try:
                            await loop.run_in_executor(None, lambda: self._driver.get("about:blank"))
                            logger.debug("WebDriver测试成功")
                            break
                        except Exception as test_e:
                            logger.warning(f"WebDriver测试失败，将重试: {str(test_e)}")
                            await self._close_driver()
                            retry_count += 1
                    else:
                        logger.error("创建WebDriver实例失败，将重试")
                        retry_count += 1
                except Exception as e:
                    logger.error(f"获取WebDriver实例时出错: {str(e)}")
                    retry_count += 1
                    
                    # 在重试之前等待一小段时间
                    if retry_count < max_retries:
                        await asyncio.sleep(1)
            
            if retry_count >= max_retries and not self._driver:
                logger.error(f"在 {max_retries} 次尝试后仍无法创建WebDriver实例")
                
        else:
            logger.debug("重用现有WebDriver实例")
            
            # 检查现有的WebDriver是否仍然可用
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: self._driver.current_url)
                logger.debug("现有WebDriver实例有效")
            except Exception as e:
                logger.warning(f"现有WebDriver实例无效，将创建新实例: {str(e)}")
                await self._close_driver()
                return await self._get_driver()  # 递归调用以创建新实例
                
        return self._driver
    
    async def _close_driver(self):
        """
        关闭WebDriver实例并清理资源
        包含失败后的后备清理措施
        """
        if self._driver:
            logger.info("关闭WebDriver实例")
            try:
                # 尝试优雅地关闭WebDriver
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._driver.quit)
                logger.info("WebDriver实例已优雅关闭")
            except Exception as e:
                logger.warning(f"标准方式关闭WebDriver实例时出错: {str(e)}")
                
                # 如果标准关闭失败，尝试通过PID强制终止进程
                if self._driver_pid:
                    try:
                        logger.info(f"尝试通过PID {self._driver_pid} 强制终止ChromeDriver进程")
                        import signal
                        os.kill(self._driver_pid, signal.SIGTERM)
                        logger.info(f"已发送SIGTERM信号到进程 {self._driver_pid}")
                        
                        # 等待进程结束
                        await asyncio.sleep(0.5)
                        
                        # 检查进程是否仍在运行
                        try:
                            os.kill(self._driver_pid, 0)  # 发送空信号来检查进程
                            # 如果没有异常，进程仍在运行，使用SIGKILL
                            logger.warning(f"进程 {self._driver_pid} 仍在运行，发送SIGKILL")
                            os.kill(self._driver_pid, signal.SIGKILL)
                        except OSError:
                            # 进程已经终止
                            logger.info(f"进程 {self._driver_pid} 已终止")
                    except Exception as kill_e:
                        logger.warning(f"无法通过PID终止ChromeDriver进程: {str(kill_e)}")
            finally:
                # 无论成功与否，都重置driver和pid
                self._driver = None
                self._driver_pid = None
    
    async def close(self):
        """
        关闭资源
        """
        await self._close_driver()
        await super().close() 