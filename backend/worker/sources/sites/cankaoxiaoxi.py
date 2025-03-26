import logging
import datetime
import asyncio
import time
from typing import List, Dict, Any, Optional

from worker.sources.base import NewsItemModel
from worker.sources.rest_api import RESTNewsSource

logger = logging.getLogger(__name__)


class CanKaoXiaoXiNewsSource(RESTNewsSource):
    """
    参考消息新闻源适配器
    优化版本：添加缓存机制、并行请求处理和超时控制
    """
    
    def __init__(
        self,
        source_id: str = "cankaoxiaoxi",
        name: str = "参考消息",
        api_url: str = "https://china.cankaoxiaoxi.com/json/channel/zhongguo/list.json",  # 默认使用中国频道
        update_interval: int = 1800,  # 30分钟
        cache_ttl: int = 900,  # 15分钟
        category: str = "news",
        country: str = "CN",
        language: str = "zh-CN",
        config: Optional[Dict[str, Any]] = None
    ):
        config = config or {}
        config.update({
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://china.cankaoxiaoxi.com/"
            },
            "request_timeout": 10,  # 请求超时时间，秒
            "overall_timeout": 30,  # 总体超时时间，秒
            "max_retries": 2,      # 最大重试次数
            "retry_delay": 0.5     # 重试延迟，秒
        })
        
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
        
        # 参考消息有多个频道，我们需要抓取所有频道
        self.channels = ["zhongguo", "guandian", "gj"]
        
        # 添加内存缓存
        self._cache = {}
        self._cache_time = {}
        self._cache_ttl = 1800  # 30分钟缓存有效期
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        重写fetch方法，并行抓取多个频道，并增加超时和缓存控制
        """
        logger.info(f"开始获取参考消息数据，频道: {self.channels}")
        start_time = time.time()
        
        # 首先检查缓存是否有效
        current_time = time.time()
        if self._cache and all(current_time - self._cache_time.get(channel, 0) < self._cache_ttl for channel in self.channels):
            cached_items = []
            for channel in self.channels:
                cached_items.extend(self._cache.get(channel, []))
            
            if cached_items:
                # 按日期排序
                cached_items.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.now(), reverse=True)
                logger.info(f"从缓存获取到 {len(cached_items)} 条参考消息新闻（{len(self.channels)}个频道）, 用时: {time.time() - start_time:.2f}秒")
                return cached_items
        
        # 设置总体超时
        overall_timeout = self.config.get("overall_timeout", 30)
        
        try:
            # 创建异步任务
            fetch_task = asyncio.create_task(self._fetch_all_channels())
            
            # 使用超时控制
            try:
                news_items = await asyncio.wait_for(fetch_task, timeout=overall_timeout)
                logger.info(f"成功获取 {len(news_items)} 条参考消息新闻, 用时: {time.time() - start_time:.2f}秒")
                return news_items
            except asyncio.TimeoutError:
                logger.warning(f"获取参考消息数据超时（{overall_timeout}秒），尝试返回部分数据")
                # 尝试返回已有的缓存数据
                cached_items = []
                for channel in self.channels:
                    cached_items.extend(self._cache.get(channel, []))
                
                if cached_items:
                    # 按日期排序
                    cached_items.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.now(), reverse=True)
                    logger.info(f"超时后从缓存返回 {len(cached_items)} 条新闻, 总用时: {time.time() - start_time:.2f}秒")
                    return cached_items
                
                logger.error("获取参考消息数据超时且没有缓存数据")
                return []
        except Exception as e:
            logger.error(f"获取参考消息数据时发生错误: {str(e)}")
            # 尝试返回缓存数据
            cached_items = []
            for channel in self.channels:
                cached_items.extend(self._cache.get(channel, []))
            
            if cached_items:
                # 按日期排序
                cached_items.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.now(), reverse=True)
                logger.info(f"错误后从缓存返回 {len(cached_items)} 条新闻")
                return cached_items
            
            raise
    
    async def _fetch_all_channels(self) -> List[NewsItemModel]:
        """并行获取所有频道的数据"""
        # 创建任务列表，并行抓取所有频道
        tasks = []
        for channel in self.channels:
            tasks.append(self._fetch_channel(channel))
        
        # 并行执行所有任务
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        news_items = []
        for channel, result in zip(self.channels, results):
            if isinstance(result, Exception):
                logger.error(f"抓取频道 {channel} 时出错: {str(result)}")
                # 使用缓存数据（如果有）
                if channel in self._cache:
                    logger.info(f"从缓存加载频道 {channel} 的数据")
                    news_items.extend(self._cache[channel])
            else:
                news_items.extend(result)
        
        # 按日期排序
        news_items.sort(key=lambda x: x.published_at if x.published_at else datetime.datetime.now(), reverse=True)
        
        return news_items
    
    async def _fetch_channel(self, channel: str) -> List[NewsItemModel]:
        """获取单个频道的数据"""
        try:
            # 构建频道URL
            channel_url = f"https://china.cankaoxiaoxi.com/json/channel/{channel}/list.json"
            
            # 获取 HTTP 客户端
            client = await self.http_client
            
            # 设置请求超时
            timeout = self.config.get("request_timeout", 10)
            
            # 获取最大重试次数和重试延迟
            max_retries = self.config.get("max_retries", 2)
            retry_delay = self.config.get("retry_delay", 0.5)
            
            # 重试机制
            for retry in range(max_retries + 1):
                try:
                    # 发送请求
                    logger.info(f"获取频道 {channel} 的数据, URL: {channel_url}")
                    async with client.get(channel_url, headers=self.headers, timeout=timeout) as response:
                        # 解析响应
                        if response.status == 200:
                            data = await response.json()
                            
                            # 使用自定义解析器处理数据
                            channel_items = self.custom_parser(data)
                            logger.info(f"成功获取频道 {channel} 的 {len(channel_items)} 条新闻")
                            
                            # 更新缓存
                            self._cache[channel] = channel_items
                            self._cache_time[channel] = time.time()
                            
                            return channel_items
                        else:
                            logger.error(f"获取频道 {channel} 数据失败, 状态码: {response.status}")
                            # 如果不是最后一次重试，等待后继续
                            if retry < max_retries:
                                await asyncio.sleep(retry_delay * (retry + 1))
                            else:
                                # 最后一次重试失败，使用缓存（如果有）
                                if channel in self._cache:
                                    logger.info(f"从缓存返回频道 {channel} 的数据")
                                    return self._cache[channel]
                                return []
                except asyncio.TimeoutError:
                    logger.warning(f"获取频道 {channel} 数据超时")
                    # 如果不是最后一次重试，等待后继续
                    if retry < max_retries:
                        await asyncio.sleep(retry_delay * (retry + 1))
                    else:
                        # 最后一次重试失败，使用缓存（如果有）
                        if channel in self._cache:
                            logger.info(f"超时后从缓存返回频道 {channel} 的数据")
                            return self._cache[channel]
                        return []
                except Exception as e:
                    logger.error(f"获取频道 {channel} 数据时出错: {str(e)}")
                    # 如果不是最后一次重试，等待后继续
                    if retry < max_retries:
                        await asyncio.sleep(retry_delay * (retry + 1))
                    else:
                        # 最后一次重试失败，使用缓存（如果有）
                        if channel in self._cache:
                            logger.info(f"错误后从缓存返回频道 {channel} 的数据")
                            return self._cache[channel]
                        return []
            
            # 所有重试都失败，返回空列表
            logger.error(f"无法获取频道 {channel} 的数据，所有重试均失败")
            return []
        except Exception as e:
            logger.error(f"处理频道 {channel} 时发生未知错误: {str(e)}")
            # 使用缓存（如果有）
            if channel in self._cache:
                logger.info(f"错误后从缓存返回频道 {channel} 的数据")
                return self._cache[channel]
            return []
    
    def custom_parser(self, data: Dict[str, Any]) -> List[NewsItemModel]:
        """
        自定义解析器，处理参考消息的JSON数据
        """
        news_items = []
        
        try:
            # 获取新闻列表
            news_list = data.get("list", [])
            
            for item in news_list:
                try:
                    # 获取新闻数据
                    news_data = item.get("data", {})
                    
                    # 获取ID
                    item_id = news_data.get("id")
                    if not item_id:
                        continue
                    
                    # 获取标题
                    title = news_data.get("title")
                    if not title:
                        continue
                    
                    # 获取URL
                    url = news_data.get("url")
                    if not url:
                        continue
                    
                    # 获取发布时间
                    publish_time = news_data.get("publishTime")
                    published_at = None
                    if publish_time:
                        try:
                            # 参考消息的时间格式为：2023-04-01 12:34:56
                            published_at = datetime.datetime.strptime(publish_time, "%Y-%m-%d %H:%M:%S")
                        except Exception as e:
                            logger.error(f"解析日期 {publish_time} 时出错: {str(e)}")
                    
                    # 创建新闻项
                    news_item = self.create_news_item(
                        id=self.generate_id(item_id),
                        title=title,
                        url=url,
                        content=news_data.get("content", ""),
                        summary=news_data.get("brief", ""),
                        image_url=news_data.get("picUrl", ""),
                        published_at=published_at,
                        extra={
                            "is_top": False,
                            "mobile_url": url,  # 参考消息的移动版URL与PC版相同
                            "source_name": self.name,
                            "category": news_data.get("category", ""),
                            "original_source": news_data.get("source", "")
                        }
                    )
                    
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"处理参考消息新闻项时出错: {str(e)}")
                    continue
        except Exception as e:
            logger.error(f"解析参考消息响应时出错: {str(e)}")
        
        return news_items
    
    # 清理缓存
    async def clear_cache(self):
        """清理缓存数据"""
        self._cache.clear()
        self._cache_time.clear()
        logger.info("已清理参考消息缓存")
    
    # 重写关闭方法，确保清理资源
    async def close(self):
        """关闭资源"""
        await self.clear_cache()
        await super().close() 