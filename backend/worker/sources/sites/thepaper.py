import json
import logging
import datetime
import re
from typing import List, Dict, Any

from bs4 import BeautifulSoup
from worker.sources.base import NewsSource, NewsItemModel

logger = logging.getLogger(__name__)


class ThePaperHotNewsSource(NewsSource):
    """
    澎湃新闻热榜适配器
    """
    def __init__(self, **kwargs):
        super().__init__(
            source_id="thepaper",
            name="澎湃新闻热榜",
            category="news",
            country="CN",
            language="zh-CN",
            update_interval=600,  # 10分钟更新一次
            config=kwargs
        )
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        抓取澎湃新闻热榜
        """
        logger.info("Fetching ThePaper hot news")
        
        # 方法0: 首先尝试从第三方API获取热榜数据
        items = await self._fetch_from_third_party_api()
        if items:
            logger.info(f"Successfully extracted {len(items)} items from third-party API")
            return items
        
        url = "https://www.thepaper.cn/"
        
        try:
            # 获取HTTP客户端
            client = self.http_client
            
            # 发送请求获取网页内容
            async with client.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch ThePaper hot news: {response.status}")
                    return []
                
                html_content = await response.text()
                
                # 记录HTML内容的一部分，用于调试
                logger.debug(f"HTML content snippet: {html_content[:500]}...")
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 方法1: 尝试从HTML结构中获取热榜数据
            items = await self._extract_from_html(soup)
            if items:
                logger.info(f"Successfully extracted {len(items)} items from HTML structure")
                return items
            
            # 方法2: 尝试从JavaScript数据中获取热榜数据
            items = await self._extract_from_javascript(soup)
            if items:
                logger.info(f"Successfully extracted {len(items)} items from JavaScript data")
                return items
            
            # 方法3: 尝试从API获取热榜数据
            items = await self._fetch_from_api()
            if items:
                logger.info(f"Successfully extracted {len(items)} items from API")
                return items
            
            logger.error("Failed to extract hot news items using any method")
            return []
        
        except Exception as e:
            logger.error(f"Error fetching ThePaper hot news: {str(e)}")
            return []
    
    async def _fetch_from_third_party_api(self) -> List[NewsItemModel]:
        """
        从第三方API获取澎湃新闻热榜数据
        """
        try:
            # 使用第三方API获取热榜数据
            third_party_api_url = "https://api.vvhan.com/api/hotlist/pengPai"
            
            logger.info(f"Fetching hot news from third-party API: {third_party_api_url}")
            
            client = self.http_client
            
            async with client.get(third_party_api_url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch from third-party API: {response.status}")
                    return []
                
                data = await response.json()
                
                # 检查返回的数据
                if not data:
                    logger.error("Empty response from third-party API")
                    return []
                
                # 检查API返回格式
                if 'success' not in data or not data['success']:
                    logger.error(f"API returned error: {data.get('message', 'Unknown error')}")
                    return []
                
                # 获取热榜数据
                hot_news_data = data.get('data', [])
                
                if not hot_news_data:
                    logger.error("No hot news data found in third-party API response")
                    return []
                
                logger.info(f"Found {len(hot_news_data)} items in third-party API response")
                
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
                        
                        # 创建新闻项
                        news_item = self.create_news_item(
                            id=self.generate_id(url, title),
                            title=title,
                            url=url,
                            summary="",  # API没有提供摘要
                            image_url="",  # API没有提供图片
                            published_at=datetime.datetime.now(),  # 使用当前时间
                            extra={
                                "rank": rank,
                                "hot": hot_value
                            }
                        )
                        
                        items.append(news_item)
                        logger.debug(f"Processed item {rank}: {title}")
                    except Exception as e:
                        logger.error(f"Error processing third-party API item at index {index}: {str(e)}")
                
                return items
        
        except Exception as e:
            logger.error(f"Error fetching from third-party API: {str(e)}")
            return []
    
    async def _extract_from_html(self, soup: BeautifulSoup) -> List[NewsItemModel]:
        """
        从HTML结构中提取热榜数据
        """
        try:
            # 根据用户提供的HTML结构，直接查找热榜容器
            hot_news_container = soup.find('div', class_='index_ppreport__slNZB index_notranstion__R0Uwz')
            logger.debug(f"hot_news_container HTML: {hot_news_container}")
            if not hot_news_container:
                logger.error("Hot news container not found with exact class names")
                # 尝试使用lambda函数查找同时包含两个类名的div
                hot_news_container = soup.find('div', class_=lambda c: c and 'index_ppreport__slNZB' in c and 'index_notranstion__R0Uwz' in c)
                if hot_news_container:
                    logger.info("Found hot news container using lambda function")
                else:
                    # 尝试使用CSS选择器查找
                    hot_news_container = soup.select_one('div.index_ppreport__slNZB.index_notranstion__R0Uwz')
                    if hot_news_container:
                        logger.info("Found hot news container using CSS selector")
                    else:
                        logger.error("Hot news container not found with any method")
                        return []
            else:
                logger.info("Found hot news container with exact class names")
            
            # 查找内容区域
            content_div = hot_news_container.find('div', class_='index_content___Uhtm')
            if not content_div:
                logger.error("Content div not found")
                return []
            
            # 查找ul元素
            ul_element = content_div.find('ul')
            if not ul_element:
                logger.error("UL element not found in content div")
                return []
            
            # 查找所有li元素
            li_elements = ul_element.find_all('li')
            if not li_elements:
                logger.error("No LI elements found in UL")
                logger.debug(f"UL element HTML: {ul_element}")
                return []
            
            logger.info(f"Found {len(li_elements)} hot news items")
            
            items = []
            for index, li in enumerate(li_elements):
                try:
                    # 查找mdCard
                    md_card = li.find('div', class_='mdCard')
                    if not md_card:
                        logger.warning(f"mdCard not found in li element at index {index}")
                        continue
                    
                    # 获取排名 - 排名在i标签中
                    rank_element = md_card.find('i')
                    rank = index + 1  # 默认使用索引+1作为排名
                    if rank_element:
                        try:
                            rank_text = rank_element.text.strip()
                            if rank_text.isdigit():
                                rank = int(rank_text)
                        except (ValueError, AttributeError):
                            logger.warning(f"Failed to parse rank from {rank_element}")
                    
                    # 获取排名颜色
                    rank_color = ""
                    if rank_element and rank_element.get('style'):
                        style = rank_element.get('style', '')
                        color_match = re.search(r'color:\s*(.*?);', style)
                        if color_match:
                            rank_color = color_match.group(1).strip()
                    
                    # 获取链接元素
                    link_element = md_card.find('a', class_='index_inherit__A1ImK')
                    if not link_element:
                        logger.warning(f"Link element not found in mdCard at index {index}")
                        continue
                    
                    # 获取标题
                    title = link_element.text.strip()
                    if not title:
                        logger.warning(f"Empty title in link at index {index}")
                        continue
                    
                    # 获取URL
                    url_path = link_element.get('href', '')
                    if not url_path:
                        logger.warning(f"Empty URL in link at index {index}")
                        continue
                    
                    # 构建完整URL
                    if url_path.startswith('http'):
                        full_url = url_path
                    else:
                        full_url = f"https://www.thepaper.cn{url_path}"
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=self.generate_id(full_url, title),
                        title=title,
                        url=full_url,
                        summary="",  # 热榜页面没有摘要
                        image_url="",  # 热榜页面没有图片
                        published_at=datetime.datetime.now(),  # 使用当前时间
                        extra={
                            "rank": rank,
                            "rank_color": rank_color
                        }
                    )
                    
                    items.append(news_item)
                    logger.debug(f"Processed item {rank}: {title}")
                except Exception as e:
                    logger.error(f"Error processing item at index {index}: {str(e)}")
            
            return items
        except Exception as e:
            logger.error(f"Error extracting from HTML: {str(e)}")
            return []
    
    async def _extract_from_javascript(self, soup: BeautifulSoup) -> List[NewsItemModel]:
        """
        从JavaScript数据中提取热榜数据
        """
        try:
            # 查找所有script标签
            scripts = soup.find_all('script')
            
            # 查找可能包含热榜数据的script
            hot_news_data = None
            for script in scripts:
                if not script.string:
                    continue
                
                script_text = script.string.lower()
                
                # 查找包含热榜相关关键词的script
                if '热榜' in script_text or 'rebang' in script_text or 'hotnews' in script_text:
                    logger.info("Found script that might contain hot news data")
                    
                    # 尝试提取JSON数据
                    try:
                        # 查找可能的JSON对象
                        json_pattern = r'({.*?})'
                        json_matches = re.findall(json_pattern, script.string, re.DOTALL)
                        
                        for json_str in json_matches:
                            try:
                                data = json.loads(json_str)
                                
                                # 检查是否包含热榜数据
                                if isinstance(data, dict):
                                    # 查找可能包含热榜数据的键
                                    for key in data:
                                        if isinstance(data[key], list) and len(data[key]) > 0:
                                            # 检查列表项是否包含标题和URL
                                            first_item = data[key][0]
                                            if isinstance(first_item, dict) and ('title' in first_item or 'url' in first_item):
                                                hot_news_data = data[key]
                                                logger.info(f"Found hot news data in script: {len(hot_news_data)} items")
                                                break
                            except json.JSONDecodeError:
                                continue
                        
                        if hot_news_data:
                            break
                    except Exception as e:
                        logger.error(f"Error parsing script: {str(e)}")
            
            if not hot_news_data:
                # 尝试查找__NEXT_DATA__，这是Next.js应用常用的数据存储方式
                next_data = soup.find('script', id='__NEXT_DATA__')
                if next_data and next_data.string:
                    try:
                        data = json.loads(next_data.string)
                        # 递归查找可能包含热榜数据的列表
                        hot_news_data = self._find_hot_news_in_data(data)
                        if hot_news_data:
                            logger.info(f"Found hot news data in __NEXT_DATA__: {len(hot_news_data)} items")
                    except Exception as e:
                        logger.error(f"Error parsing __NEXT_DATA__: {str(e)}")
            
            if not hot_news_data:
                logger.error("No hot news data found in JavaScript")
                return []
            
            # 处理提取到的数据
            items = []
            for index, item_data in enumerate(hot_news_data):
                try:
                    # 提取标题和URL
                    title = item_data.get('title', '')
                    url_path = item_data.get('url', '')
                    
                    # 如果没有title或url，尝试其他可能的键名
                    if not title:
                        for key in item_data:
                            if 'title' in key.lower():
                                title = item_data[key]
                                break
                    
                    if not url_path:
                        for key in item_data:
                            if 'url' in key.lower() or 'link' in key.lower() or 'href' in key.lower():
                                url_path = item_data[key]
                                break
                    
                    if not title or not url_path:
                        continue
                    
                    # 构建完整URL
                    if url_path.startswith('http'):
                        full_url = url_path
                    else:
                        full_url = f"https://www.thepaper.cn{url_path}"
                    
                    # 获取排名
                    rank = item_data.get('rank', index + 1)
                    if not isinstance(rank, int):
                        try:
                            rank = int(rank)
                        except (ValueError, TypeError):
                            rank = index + 1
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=self.generate_id(full_url, title),
                        title=title,
                        url=full_url,
                        summary="",
                        image_url="",
                        published_at=datetime.datetime.now(),
                        extra={
                            "rank": rank
                        }
                    )
                    
                    items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing JavaScript item at index {index}: {str(e)}")
            
            return items
        except Exception as e:
            logger.error(f"Error extracting from JavaScript: {str(e)}")
            return []
    
    def _find_hot_news_in_data(self, data, max_depth=5, current_depth=0):
        """
        递归查找数据中可能包含热榜的列表
        """
        if current_depth >= max_depth:
            return None
        
        if isinstance(data, list) and len(data) > 0:
            # 检查是否是热榜数据
            if all(isinstance(item, dict) for item in data):
                # 检查列表项是否包含标题和URL
                has_title = any('title' in item for item in data)
                has_url = any('url' in item for item in data)
                
                if has_title and has_url:
                    return data
        
        if isinstance(data, dict):
            # 优先查找可能包含热榜的键
            for key in ['hotNews', 'rebang', 'hot', '热榜', 'topNews', 'top']:
                if key in data and isinstance(data[key], list) and len(data[key]) > 0:
                    result = self._find_hot_news_in_data(data[key], max_depth, current_depth + 1)
                    if result:
                        return result
            
            # 递归查找所有键
            for key in data:
                result = self._find_hot_news_in_data(data[key], max_depth, current_depth + 1)
                if result:
                    return result
        
        return None
    
    async def _fetch_from_api(self) -> List[NewsItemModel]:
        """
        从API获取热榜数据
        """
        try:
            # 尝试从可能的API端点获取热榜数据
            api_urls = [
                "https://www.thepaper.cn/api/getHotNews",
                "https://www.thepaper.cn/api/getTopNews",
                "https://www.thepaper.cn/api/getRebang"
            ]
            
            client = self.http_client
            
            for api_url in api_urls:
                try:
                    logger.info(f"Trying to fetch hot news from API: {api_url}")
                    
                    async with client.get(api_url) as response:
                        if response.status != 200:
                            logger.warning(f"Failed to fetch from API {api_url}: {response.status}")
                            continue
                        
                        data = await response.json()
                        
                        # 检查返回的数据
                        if not data:
                            logger.warning(f"Empty response from API {api_url}")
                            continue
                        
                        # 查找可能包含热榜数据的列表
                        hot_news_data = None
                        
                        if isinstance(data, list) and len(data) > 0:
                            hot_news_data = data
                        elif isinstance(data, dict):
                            # 查找可能包含热榜数据的键
                            for key in data:
                                if isinstance(data[key], list) and len(data[key]) > 0:
                                    hot_news_data = data[key]
                                    break
                        
                        if not hot_news_data:
                            logger.warning(f"No hot news data found in API response from {api_url}")
                            continue
                        
                        # 处理提取到的数据
                        items = []
                        for index, item_data in enumerate(hot_news_data):
                            try:
                                # 提取标题和URL
                                title = item_data.get('title', '')
                                url_path = item_data.get('url', '')
                                
                                # 如果没有title或url，尝试其他可能的键名
                                if not title:
                                    for key in item_data:
                                        if 'title' in key.lower():
                                            title = item_data[key]
                                            break
                                
                                if not url_path:
                                    for key in item_data:
                                        if 'url' in key.lower() or 'link' in key.lower() or 'href' in key.lower():
                                            url_path = item_data[key]
                                            break
                                
                                if not title or not url_path:
                                    continue
                                
                                # 构建完整URL
                                if url_path.startswith('http'):
                                    full_url = url_path
                                else:
                                    full_url = f"https://www.thepaper.cn{url_path}"
                                
                                # 获取排名
                                rank = item_data.get('rank', index + 1)
                                if not isinstance(rank, int):
                                    try:
                                        rank = int(rank)
                                    except (ValueError, TypeError):
                                        rank = index + 1
                                
                                # 创建新闻项
                                news_item = self.create_news_item(
                                    id=self.generate_id(full_url, title),
                                    title=title,
                                    url=full_url,
                                    summary="",
                                    image_url="",
                                    published_at=datetime.datetime.now(),
                                    extra={
                                        "rank": rank
                                    }
                                )
                                
                                items.append(news_item)
                            except Exception as e:
                                logger.error(f"Error processing API item at index {index}: {str(e)}")
                        
                        if items:
                            logger.info(f"Successfully fetched {len(items)} items from API {api_url}")
                            return items
                
                except Exception as e:
                    logger.error(f"Error fetching from API {api_url}: {str(e)}")
            
            logger.error("Failed to fetch hot news from any API")
            return []
        
        except Exception as e:
            logger.error(f"Error fetching from API: {str(e)}")
            return [] 