import logging
import datetime
import hashlib
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
import re
from urllib.parse import urlparse, parse_qs, unquote

from worker.sources.base import NewsItemModel
from worker.sources.rest_api import RESTNewsSource
from worker.utils.http_client import http_client

logger = logging.getLogger(__name__)


class LinuxDoNewsSource(RESTNewsSource):
    """
    Linux迷新闻源适配器
    原始 linux.do 站点可能会返回 403 错误，
    此适配器添加了备用来源，包括 LinuxCN 和 LinuxStory，
    以确保即使原始 API 不可用也能获取到相关内容。
    """
    
    # 备用源 RSS 源
    BACKUP_URLS = [
        "https://linux.cn/rss.xml",              # Linux中国 RSS 源
        "https://linuxstory.org/feed/",          # LinuxStory RSS 源
    ]
    
    def __init__(
        self,
        source_id: str = "linuxdo",
        name: str = "Linux迷",
        api_url: str = "https://linux.do/latest.json?order=created",
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "technology",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None,
        mode: str = "latest"  # 模式：latest 或 hot
    ):
        self.mode = mode
        
        # 根据模式设置API URL
        if mode == "hot":
            api_url = "https://linux.do/top/daily.json"
        
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                "Accept": "application/json, application/xml, text/xml, application/rss+xml, */*",
                "Referer": "https://www.google.com/",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "DNT": "1",
                "Connection": "keep-alive"
            },
            "max_retries": 3,
            "retry_delay": 2,
            "timeout": 20,
            "use_backup_sources": True
        })
        
        self.backup_urls = config.get("backup_urls", self.BACKUP_URLS)
        
        super().__init__(
            source_id=source_id,
            name=name,
            api_url=api_url,
            update_interval=update_interval,
            cache_ttl=cache_ttl,
            category=category,
            country=country,
            language=language,
            custom_parser=self.custom_parser
        )
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        获取Linux相关新闻，添加错误处理和备用源
        """
        logger.info(f"正在从主要API获取Linux新闻: {self.api_url}")
        
        news_items = []
        try:
            # 尝试从原始API获取数据
            response = await http_client.fetch(
                url=self.api_url,
                method="GET",
                params=self.params,
                headers=self.headers,
                response_type="json",
                timeout=self.config.get("timeout", 15)
            )
            
            # 使用解析器处理响应
            news_items = self.custom_parser(response)
            logger.info(f"从原始API获取到 {len(news_items)} 条新闻")
            
        except Exception as e:
            logger.warning(f"原始API请求失败: {str(e)}")
            
            # 如果启用了备用源选项，尝试从备用源获取数据
            if self.config.get("use_backup_sources", True) and self.backup_urls:
                logger.info("尝试使用备用源获取数据...")
                backup_items = await self._fetch_from_backup_sources()
                
                if backup_items:
                    logger.info(f"从备用源获取到 {len(backup_items)} 条新闻")
                    news_items = backup_items
                else:
                    logger.warning("备用源也未能获取数据")
                    # 不再创建模拟数据，而是抛出异常
                    raise RuntimeError("无法获取Linux新闻数据：原始API和所有备用源均失败")
            else:
                # 不再创建模拟数据，而是抛出异常
                logger.error("原始API失败且未启用备用源")
                raise RuntimeError(f"无法获取Linux新闻数据：API请求失败 - {str(e)}")
        
        return news_items
    
    async def _fetch_from_backup_sources(self) -> List[NewsItemModel]:
        """
        从备用RSS源获取数据
        """
        news_items = []
        
        for url in self.backup_urls:
            try:
                logger.info(f"尝试从备用源获取数据: {url}")
                
                response = await http_client.fetch(
                    url=url,
                    method="GET",
                    headers=self.headers,
                    response_type="text",
                    timeout=self.config.get("timeout", 15)
                )
                
                # 解析RSS响应
                items = await self._parse_rss(response, url)
                
                if items:
                    news_items.extend(items)
                    logger.info(f"从 {url} 获取到 {len(items)} 条新闻")
                    
                    # 如果获取足够的条目，就停止
                    if len(news_items) >= 30:
                        break
            except Exception as e:
                logger.warning(f"从备用源 {url} 获取数据失败: {str(e)}")
        
        # 根据模式排序
        if self.mode == "latest":
            # 按发布时间排序（最新的在前）
            news_items.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.now(datetime.timezone.utc), reverse=True)
        else:
            # 热门模式下，使用随机顺序
            import random
            random.shuffle(news_items)
        
        return news_items[:50]  # 限制返回的条目数
    
    async def _parse_rss(self, content: str, source_url: str) -> List[NewsItemModel]:
        """
        解析RSS内容并创建新闻项
        """
        news_items = []
        source_domain = urlparse(source_url).netloc
        
        try:
            # 处理可能的XML声明问题
            if not content.strip().startswith('<?xml'):
                content = f'<?xml version="1.0" encoding="UTF-8"?>{content}'
            
            # 解析XML
            root = ET.fromstring(content)
            
            # 查找RSS中的item元素
            channel = root.find('channel')
            if channel is None:
                return []
                
            items = channel.findall('item')
            
            for item in items:
                try:
                    # 获取标题
                    title_elem = item.find('title')
                    if title_elem is None or not title_elem.text:
                        continue
                    
                    # 处理CDATA包装的标题
                    title = title_elem.text
                    if title.startswith('<![CDATA[') and title.endswith(']]>'):
                        title = title[9:-3]
                    
                    # 获取链接
                    link_elem = item.find('link')
                    if link_elem is None or not link_elem.text:
                        continue
                    url = link_elem.text
                    
                    # 生成唯一ID
                    item_id = hashlib.md5(f"{self.source_id}:{url}".encode()).hexdigest()
                    
                    # 获取发布时间
                    published_at = None
                    pub_date_elem = item.find('pubDate')
                    if pub_date_elem is not None and pub_date_elem.text:
                        try:
                            from email.utils import parsedate_to_datetime
                            published_at = parsedate_to_datetime(pub_date_elem.text)
                        except:
                            pass
                    
                    # 获取描述/摘要
                    summary = None
                    desc_elem = item.find('description')
                    if desc_elem is not None and desc_elem.text:
                        # 提取纯文本，移除HTML标签
                        summary_text = desc_elem.text
                        if summary_text.startswith('<![CDATA[') and summary_text.endswith(']]>'):
                            summary_text = summary_text[9:-3]
                        
                        summary = re.sub(r'<[^>]+>', ' ', summary_text)
                        summary = re.sub(r'\s+', ' ', summary).strip()
                    
                    # 获取作者
                    author = None
                    creator_elem = item.find('.//{http://purl.org/dc/elements/1.1/}creator')
                    if creator_elem is not None and creator_elem.text:
                        author_text = creator_elem.text
                        if author_text.startswith('<![CDATA[') and author_text.endswith(']]>'):
                            author = author_text[9:-3]
                        else:
                            author = author_text
                    
                    # 获取分类
                    categories = []
                    for cat_elem in item.findall('category'):
                        if cat_elem.text:
                            cat_text = cat_elem.text
                            if cat_text.startswith('<![CDATA[') and cat_text.endswith(']]>'):
                                categories.append(cat_text[9:-3])
                            else:
                                categories.append(cat_text)
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=item_id,
                        title=title,
                        url=url,
                        content=None,
                        summary=summary,
                        image_url=None,
                        published_at=published_at,
                        extra={
                            "is_top": False,
                            "mobile_url": url,
                            "author": author,
                            "categories": categories,
                            "source_from": f"rss:{source_domain}"
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"处理RSS条目时出错: {str(e)}")
                    continue
            
            return news_items
        
        except Exception as e:
            logger.error(f"解析RSS内容时出错: {str(e)}")
            return []
    
    def custom_parser(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """
        自定义解析器，处理Linux中国的JSON数据
        """
        news_items = []
        
        try:
            # 获取主题列表
            topic_list = data.get("topic_list", {})
            topics = topic_list.get("topics", [])
            
            for topic in topics:
                try:
                    # 检查主题是否可见、未归档、未置顶
                    visible = topic.get("visible", False)
                    archived = topic.get("archived", False)
                    pinned = topic.get("pinned", False)
                    
                    if not visible or archived:
                        continue
                    
                    # 获取主题ID
                    topic_id = topic.get("id")
                    if not topic_id:
                        continue
                    
                    # 获取标题
                    title = topic.get("title")
                    if not title:
                        continue
                    
                    # 生成URL
                    url = f"https://linux.do/t/topic/{topic_id}"
                    
                    # 获取创建时间
                    created_at_str = topic.get("created_at")
                    published_at = None
                    if created_at_str:
                        try:
                            published_at = datetime.datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                        except Exception as e:
                            logger.error(f"Error parsing date {created_at_str}: {str(e)}")
                    
                    # 获取摘要
                    excerpt = topic.get("excerpt")
                    
                    # 获取回复数和点赞数
                    reply_count = topic.get("reply_count", 0)
                    like_count = topic.get("like_count", 0)
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=str(topic_id),
                        title=title,
                        url=url,
                        content=None,
                        summary=excerpt,
                        image_url=None,
                        published_at=published_at,
                        extra={
                            "is_top": pinned,
                            "mobile_url": url,
                            "like_count": like_count,
                            "comment_count": reply_count,
                            "info": f"👍 {like_count} 💬 {reply_count}",
                            "source_from": "linux.do"
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error processing LinuxDo topic: {str(e)}")
                    continue
            
            # 如果是最新模式，按创建时间排序
            if self.mode == "latest":
                news_items.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.now(datetime.timezone.utc), reverse=True)
            
            return news_items
        except Exception as e:
            logger.error(f"Error parsing LinuxDo response: {str(e)}")
            return []
    
    def _create_mock_data(self) -> List[NewsItemModel]:
        """
        创建模拟数据作为最后的备用选项
        """
        logger.info("创建Linux相关模拟数据")
        
        # 模拟标题和URL模板
        mock_items = [
            {
                "title": "如何在Linux中使用Docker容器化应用程序",
                "url": "https://linux.cn/article-mock-1.html",
                "summary": "本教程详细介绍了Docker在Linux中的安装和基本使用方法，帮助开发者快速上手容器化技术。"
            },
            {
                "title": "Linux 6.0内核发布，带来重大性能提升",
                "url": "https://linux.cn/article-mock-2.html",
                "summary": "最新的Linux 6.0内核已发布，改进了调度器性能，增强了安全特性，并提供了更好的硬件支持。"
            },
            {
                "title": "开源人工智能工具在Linux环境下的部署指南",
                "url": "https://linux.cn/article-mock-3.html",
                "summary": "本文介绍如何在Linux系统中部署和使用流行的开源AI工具，包括TensorFlow和PyTorch框架。"
            },
            {
                "title": "Linux服务器安全加固最佳实践",
                "url": "https://linux.cn/article-mock-4.html",
                "summary": "保护你的Linux服务器免受攻击的实用技巧，从基本的用户权限管理到高级的入侵检测系统。"
            },
            {
                "title": "五个提高Linux终端效率的隐藏技巧",
                "url": "https://linux.cn/article-mock-5.html",
                "summary": "这些鲜为人知的终端使用技巧将显著提升你的命令行工作效率。"
            },
            {
                "title": "如何配置Linux系统实现最佳性能",
                "url": "https://linux.cn/article-mock-6.html",
                "summary": "从内核参数优化到文件系统选择，本文全面介绍如何调整Linux系统以获得最佳性能。"
            },
            {
                "title": "在Linux下搭建高性能Web服务器的完整指南",
                "url": "https://linux.cn/article-mock-7.html",
                "summary": "使用Nginx和优化的Linux配置，构建能够承载高流量的现代Web服务器。"
            },
            {
                "title": "Linux发行版比较：Ubuntu、Fedora和Arch的优缺点分析",
                "url": "https://linux.cn/article-mock-8.html",
                "summary": "详细对比三种流行的Linux发行版，帮助用户根据自己的需求选择最合适的系统。"
            },
            {
                "title": "如何在Linux中实现自动化系统管理",
                "url": "https://linux.cn/article-mock-9.html",
                "summary": "使用Ansible、Shell脚本和Cron作业，构建完全自动化的Linux系统管理方案。"
            },
            {
                "title": "Linux下的现代开发环境搭建",
                "url": "https://linux.cn/article-mock-10.html",
                "summary": "从代码编辑器到版本控制，从容器化工具到CI/CD管道，打造完美的Linux开发环境。"
            }
        ]
        
        now = datetime.datetime.now(datetime.timezone.utc)
        news_items = []
        
        for i, item in enumerate(mock_items):
            # 创建随机发布时间（最近7天内）
            hours_ago = i * 5 + i % 3  # 创建一些时间差异
            published_at = now - datetime.timedelta(hours=hours_ago)
            
            # 生成ID
            item_id = hashlib.md5(f"mock:{item['url']}".encode()).hexdigest()
            
            # 创建新闻项
            news_item = self.create_news_item(
                id=item_id,
                title=item["title"],
                url=item["url"],
                content=None,
                summary=item["summary"],
                image_url=None,
                published_at=published_at,
                extra={
                    "is_top": i < 3,  # 前三个是置顶
                    "mobile_url": item["url"],
                    "like_count": 10 + i * 5,
                    "comment_count": 5 + i * 2,
                    "info": f"👍 {10 + i * 5} 💬 {5 + i * 2}",
                    "source_from": "mock_data",
                    "is_mock": True
                }
            )
            
            news_items.append(news_item)
        
        return news_items


class LinuxDoLatestNewsSource(LinuxDoNewsSource):
    """
    Linux迷最新主题适配器
    """
    
    def __init__(
        self,
        source_id: str = "linuxdo-latest",
        name: str = "Linux迷最新",
        **kwargs
    ):
        super().__init__(
            source_id=source_id,
            name=name,
            mode="latest",
            **kwargs
        )


class LinuxDoHotNewsSource(LinuxDoNewsSource):
    """
    Linux迷热门主题适配器
    """
    
    def __init__(
        self,
        source_id: str = "linuxdo-hot",
        name: str = "Linux迷热门",
        **kwargs
    ):
        super().__init__(
            source_id=source_id,
            name=name,
            mode="hot",
            **kwargs
        ) 