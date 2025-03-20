import logging
import asyncio
import time
from typing import Dict, List, Optional, Type, Any, Set
from difflib import SequenceMatcher

from worker.sources.base import NewsSource, NewsItemModel
from worker.sources.factory import NewsSourceFactory
from worker.stats_wrapper import stats_updater
from worker.sources.config import settings

logger = logging.getLogger(__name__)


class NewsSourceManager:
    """
    新闻源管理器
    负责管理所有新闻源，提供统一的接口获取新闻
    """
    
    def __init__(self):
        self.sources: Dict[str, NewsSource] = {}
        self.news_cache: Dict[str, List[NewsItemModel]] = {}
        self.last_fetch_time: Dict[str, float] = {}
        self.duplicate_cache: Set[str] = set()  # 用于存储已处理的新闻标题指纹
        self.similarity_threshold = 0.85  # 相似度阈值，超过此值认为是重复新闻
    
    def register_source(self, source: NewsSource) -> None:
        """
        注册新闻源
        """
        self.sources[source.source_id] = source
        settings.log_info(f"Registered news source: {source.source_id} ({source.name})")
    
    def register_sources(self, sources: List[NewsSource]) -> None:
        """
        批量注册新闻源
        """
        for source in sources:
            self.register_source(source)
    
    def register_default_sources(self) -> None:
        """
        注册默认新闻源
        """
        # 获取所有可用的源类型
        source_types = NewsSourceFactory.get_available_sources()
        
        # 创建并注册源实例
        sources = []
        for source_type in source_types:
            try:
                source = NewsSourceFactory.create_source(source_type)
                if source:
                    sources.append(source)
            except Exception as e:
                logger.error(f"创建源 {source_type} 时出错: {str(e)}")
        
        self.register_sources(sources)
        
        # 只记录源总数，而不是每个源的详细信息
        logger.info(f"注册了 {len(self.sources)} 个新闻源")
    
    def get_source(self, source_id: str) -> Optional[NewsSource]:
        """
        获取新闻源
        """
        return self.sources.get(source_id)
    
    def get_all_sources(self) -> List[NewsSource]:
        """
        获取所有新闻源
        """
        return list(self.sources.values())
    
    def get_sources_by_category(self, category: str) -> List[NewsSource]:
        """
        按分类获取新闻源
        """
        return [source for source in self.sources.values() if source.category == category]
    
    def get_sources_by_country(self, country: str) -> List[NewsSource]:
        """
        按国家获取新闻源
        """
        return [source for source in self.sources.values() if source.country == country]
    
    def get_sources_by_language(self, language: str) -> List[NewsSource]:
        """
        按语言获取新闻源
        """
        return [source for source in self.sources.values() if source.language == language]
    
    def _generate_title_fingerprint(self, title: str) -> str:
        """
        生成标题指纹
        去除标点符号和空格，转为小写
        """
        import re
        # 去除标点符号和空格，转为小写
        return re.sub(r'[^\w\s]', '', title).lower().replace(' ', '')
    
    def _is_duplicate(self, news_item: NewsItemModel) -> bool:
        """
        判断是否是重复新闻
        使用标题相似度判断
        """
        # 生成当前新闻的标题指纹
        title_fingerprint = self._generate_title_fingerprint(news_item.title)
        
        # 如果指纹已存在，直接判定为重复
        if title_fingerprint in self.duplicate_cache:
            return True
        
        # 添加到缓存
        self.duplicate_cache.add(title_fingerprint)
        
        # 如果缓存过大，清理旧数据
        if len(self.duplicate_cache) > 10000:
            # 保留最新的5000条
            self.duplicate_cache = set(list(self.duplicate_cache)[-5000:])
        
        return False
    
    def _calculate_similarity(self, title1: str, title2: str) -> float:
        """
        计算两个标题的相似度
        使用SequenceMatcher计算
        """
        return SequenceMatcher(None, title1, title2).ratio()
    
    async def fetch_news(self, source_id: str, force_update: bool = False) -> List[NewsItemModel]:
        """
        获取指定新闻源的新闻
        支持强制更新和缓存
        """
        settings.log_info(f">>> NewsSourceManager.fetch_news called for {source_id}")
        source = self.get_source(source_id)
        if not source:
            logger.error(f"News source not found: {source_id}")
            return []
        
        current_time = time.time()
        
        # 检查是否需要更新
        if not force_update and source_id in self.news_cache:
            last_fetch = self.last_fetch_time.get(source_id, 0)
            if current_time - last_fetch < source.cache_ttl:
                logger.debug(f"Using cached news for {source_id}")
                return self.news_cache[source_id]
        
        # 获取新闻
        try:
            # 使用统计信息更新包装器包装源的get_news方法
            async def fetch_with_stats():
                settings.log_info(f">>> fetch_with_stats called for {source_id}")
                # 捕获源的fetch方法
                original_fetch = source.fetch
                settings.log_info(f">>> Original fetch method: {original_fetch}")
                
                try:
                    # 使用包装器替换原始fetch方法
                    settings.log_info(f">>> Replacing fetch method with stats_updater.wrap_fetch for {source_id}")
                    source.fetch = lambda *args, **kwargs: stats_updater.wrap_fetch(source_id, original_fetch, *args, **kwargs)
                    
                    # 调用源的get_news方法，它会使用包装后的fetch方法
                    settings.log_info(f">>> Calling source.get_news for {source_id}")
                    result = await source.get_news(force_update=force_update)
                    settings.log_info(f">>> source.get_news completed for {source_id}, received {len(result)} items")
                    return result
                finally:
                    # 恢复原始fetch方法
                    settings.log_info(f">>> Restoring original fetch method for {source_id}")
                    source.fetch = original_fetch
            
            news_items = await fetch_with_stats()
            
            # 过滤重复新闻
            unique_news = []
            for item in news_items:
                if not self._is_duplicate(item):
                    unique_news.append(item)
            
            # 更新缓存
            self.news_cache[source_id] = unique_news
            self.last_fetch_time[source_id] = current_time
            
            settings.log_info(f"Fetched {len(news_items)} news items from {source_id}, {len(unique_news)} unique")
            return unique_news
        except Exception as e:
            logger.error(f"Error fetching news from {source_id}: {str(e)}")
            return self.news_cache.get(source_id, [])
    
    async def fetch_all_news(self, force_update: bool = False) -> Dict[str, List[NewsItemModel]]:
        """
        获取所有新闻源的新闻
        """
        logger.info(f"开始获取所有新闻源新闻，强制更新：{force_update}，源数量：{len(self.sources)}")
        tasks = []
        source_ids = list(self.sources.keys())
        
        for source_id in source_ids:
            tasks.append(self.fetch_news(source_id, force_update=force_update))
        
        settings.log_info(f"创建了 {len(tasks)} 个获取新闻任务")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        news_dict = {}
        success_count = 0
        total_news_count = 0
        
        for i, source_id in enumerate(source_ids):
            result = results[i]
            if isinstance(result, Exception):
                logger.error(f"源 {source_id} 获取新闻失败: {str(result)}")
                news_dict[source_id] = []
            else:
                news_count = len(result)
                news_dict[source_id] = result
                total_news_count += news_count
                if news_count > 0:
                    success_count += 1
                    settings.log_info(f"源 {source_id} 获取到 {news_count} 条新闻")
        
        logger.info(f"获取所有新闻源完成: {success_count}/{len(source_ids)} 个源成功获取新闻，总计 {total_news_count} 条新闻")
        return news_dict
    
    async def fetch_news_by_category(self, category: str, force_update: bool = False) -> Dict[str, List[NewsItemModel]]:
        """
        按分类获取新闻
        """
        sources = self.get_sources_by_category(category)
        tasks = []
        for source in sources:
            tasks.append(self.fetch_news(source.source_id, force_update=force_update))
        
        results = await asyncio.gather(*tasks)
        
        news_dict = {}
        for i, source in enumerate(sources):
            news_dict[source.source_id] = results[i]
        
        return news_dict
    
    async def search_news(self, query: str, max_results: int = 100) -> List[NewsItemModel]:
        """
        搜索新闻
        简单的关键词匹配
        """
        query = query.lower()
        results = []
        
        # 从所有缓存的新闻中搜索
        for source_id, news_items in self.news_cache.items():
            for item in news_items:
                if query in item.title.lower() or (item.summary and query in item.summary.lower()):
                    results.append(item)
                    if len(results) >= max_results:
                        return results
        
        return results
    
    async def close(self):
        """
        关闭所有新闻源
        """
        for source in self.sources.values():
            if hasattr(source, 'close'):
                await source.close()
        
        logger.info("All news sources closed")


# 全局单例
source_manager = NewsSourceManager() 