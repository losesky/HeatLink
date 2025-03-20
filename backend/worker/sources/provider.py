from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from worker.sources.interface import NewsSourceInterface


class NewsSourceProvider(ABC):
    """
    新闻源提供者接口
    任务调度器和API接口只依赖于这个接口
    """
    
    @abstractmethod
    def get_source(self, source_id: str) -> Optional[NewsSourceInterface]:
        """
        获取新闻源
        
        Args:
            source_id: 源ID
            
        Returns:
            新闻源
        """
        pass
    
    @abstractmethod
    def get_all_sources(self) -> List[NewsSourceInterface]:
        """
        获取所有新闻源
        
        Returns:
            所有新闻源
        """
        pass
    
    @abstractmethod
    def get_sources_by_category(self, category: str) -> List[NewsSourceInterface]:
        """
        按分类获取新闻源
        
        Args:
            category: 分类
            
        Returns:
            指定分类的新闻源列表
        """
        pass


class DefaultNewsSourceProvider(NewsSourceProvider):
    """
    默认新闻源提供者实现
    使用工厂方法创建新闻源
    """
    
    def __init__(self):
        self.sources: Dict[str, NewsSourceInterface] = {}
        self._initialize_sources()
    
    def _initialize_sources(self):
        """
        初始化新闻源
        可以从工厂方法或配置文件加载
        """
        from worker.sources.factory import NewsSourceFactory
        
        # 获取所有可用的源类型
        source_types = NewsSourceFactory.get_available_sources()
        
        # 创建所有源的实例
        for source_type in source_types:
            try:
                source = NewsSourceFactory.create_source(source_type)
                if source:
                    self.sources[source.source_id] = source
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"创建源 {source_type} 时出错: {str(e)}")
    
    def get_source(self, source_id: str) -> Optional[NewsSourceInterface]:
        """
        获取新闻源
        
        Args:
            source_id: 源ID
            
        Returns:
            新闻源
        """
        return self.sources.get(source_id)
    
    def get_all_sources(self) -> List[NewsSourceInterface]:
        """
        获取所有新闻源
        
        Returns:
            所有新闻源
        """
        return list(self.sources.values())
    
    def get_sources_by_category(self, category: str) -> List[NewsSourceInterface]:
        """
        按分类获取新闻源
        
        Args:
            category: 分类
            
        Returns:
            指定分类的新闻源列表
        """
        return [source for source in self.sources.values() if source.category == category]
    
    def register_source(self, source: NewsSourceInterface):
        """
        注册新闻源
        
        Args:
            source: 新闻源
        """
        self.sources[source.source_id] = source
    
    def unregister_source(self, source_id: str):
        """
        注销新闻源
        
        Args:
            source_id: 源ID
        """
        if source_id in self.sources:
            del self.sources[source_id] 