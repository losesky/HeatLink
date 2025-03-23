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
        从数据库加载配置信息，并应用到源实例
        """
        from worker.sources.factory import NewsSourceFactory
        import logging
        logger = logging.getLogger(__name__)
        
        # 获取所有可用的源类型
        source_types = NewsSourceFactory.get_available_sources()
        
        # 尝试从数据库获取配置
        db_configs = {}
        try:
            import psycopg2
            # 连接数据库
            conn = psycopg2.connect('postgresql://postgres:postgres@localhost:5432/heatlink_dev')
            cur = conn.cursor()
            # 获取所有源的配置
            cur.execute("SELECT id, config FROM sources")
            rows = cur.fetchall()
            conn.close()
            
            # 保存到配置字典，使用小写键以便不区分大小写比较
            for row in rows:
                source_id, config = row
                # 同时保存原始ID和小写ID，确保能找到匹配
                db_configs[source_id] = config
                if source_id.lower() != source_id:
                    db_configs[source_id.lower()] = config
                
            logger.info(f"从数据库加载了 {len(rows)} 个源的配置信息")
        except Exception as e:
            logger.error(f"从数据库加载源配置失败: {str(e)}")
            logger.warning("将使用默认配置创建源实例")
        
        # 创建所有源的实例
        for source_type in source_types:
            try:
                # 检查各种可能的匹配
                found_config = None
                config_key = None
                
                # 先尝试精确匹配
                if source_type in db_configs:
                    found_config = db_configs[source_type]
                    config_key = source_type
                else:
                    # 尝试小写匹配
                    source_type_lower = source_type.lower()
                    if source_type_lower in db_configs:
                        found_config = db_configs[source_type_lower]
                        config_key = source_type_lower
                    else:
                        # 尝试短横线和下划线的替换版本
                        alt_key = source_type.replace('-', '_')
                        if alt_key in db_configs:
                            found_config = db_configs[alt_key]
                            config_key = alt_key
                        else:
                            alt_key_lower = alt_key.lower()
                            if alt_key_lower in db_configs:
                                found_config = db_configs[alt_key_lower]
                                config_key = alt_key_lower
                            else:
                                alt_key = source_type.replace('_', '-')
                                if alt_key in db_configs:
                                    found_config = db_configs[alt_key]
                                    config_key = alt_key
                                else:
                                    alt_key_lower = alt_key.lower()
                                    if alt_key_lower in db_configs:
                                        found_config = db_configs[alt_key_lower]
                                        config_key = alt_key_lower
                                    
                # 针对CLS源特殊处理
                if not found_config and (source_type.lower() == "cls" or source_type.lower() == "cls-article"):
                    # 尝试直接获取配置，因为知道source_id名称
                    exact_id = "cls" if source_type.lower() == "cls" else "cls-article"
                    if exact_id in db_configs:
                        found_config = db_configs[exact_id]
                        config_key = exact_id
                        logger.info(f"为CLS源 {source_type} 找到了特殊配置，使用ID: {exact_id}")
                        
                # 如果找到配置，使用配置创建源
                if found_config:
                    source = NewsSourceFactory.create_source(source_type, config=found_config)
                    logger.debug(f"使用数据库配置创建源 {source_type}: {found_config}")
                else:
                    source = NewsSourceFactory.create_source(source_type)
                    logger.debug(f"使用默认配置创建源 {source_type}")
                
                if source:
                    self.sources[source.source_id] = source
            except Exception as e:
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