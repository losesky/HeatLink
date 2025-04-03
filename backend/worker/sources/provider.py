from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import traceback
import logging

from worker.sources.interface import NewsSourceInterface
from worker.sources.factory import NewsSourceFactory

# 创建日志器
logger = logging.getLogger(__name__)


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
        """
        try:
            # 首先尝试从数据库加载源配置
            all_configs = self._load_sources_from_db()
            
            # 将配置按source_id索引
            db_configs = {}
            for config in all_configs:
                source_id = config.get("source_id")
                if source_id:
                    db_configs[source_id] = config
            
            if db_configs:
                logger.info(f"从数据库加载了 {len(db_configs)} 个源的配置信息")
            
            # 获取所有可用的源类型
            source_types = NewsSourceFactory.get_available_sources()
            
            # 创建所有源的实例，优先使用数据库配置
            for source_type in source_types:
                try:
                    # 尝试查找匹配的配置
                    found_config = None
                    config_key = None
                    
                    # 首先尝试精确匹配
                    if source_type in db_configs:
                        found_config = db_configs[source_type]
                        config_key = source_type
                    else:
                        # 尝试替换-和_
                        alt_source_type = source_type.replace('-', '_')
                        if alt_source_type in db_configs:
                            found_config = db_configs[alt_source_type]
                            config_key = alt_source_type
                        else:
                            alt_source_type = source_type.replace('_', '-')
                            if alt_source_type in db_configs:
                                found_config = db_configs[alt_source_type]
                                config_key = alt_source_type
                                
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
                     
        except Exception as e:
            logger.error(f"初始化新闻源出错: {str(e)}")
            logger.error(traceback.format_exc())
    
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
    
    def _load_sources_from_db(self) -> List[Dict[str, Any]]:
        """
        从数据库加载源配置
        
        Returns:
            源配置列表
        """
        configs = []
        
        try:
            # 尝试使用SQLAlchemy会话
            from app.db.session import SessionLocal
            from app.models.source import Source
            from sqlalchemy import text
            import json
            
            # 创建会话
            db = SessionLocal()
            try:
                # 获取所有源的配置
                sources = db.query(Source).all()
                
                for source in sources:
                    try:
                        # 转换配置 - 检查config是否已经是字典类型
                        if source.config:
                            if isinstance(source.config, dict):
                                config = source.config
                            else:
                                config = json.loads(source.config)
                        else:
                            config = {}
                            
                        # 将源的基本属性添加到配置中
                        config["source_id"] = source.id
                        config["name"] = source.name  # 添加源名称
                        config["url"] = source.url if hasattr(source, 'url') else ""
                        
                        # 添加其他重要属性
                        if hasattr(source, 'category_id'):
                            config["category_id"] = source.category_id
                        if hasattr(source, 'country'):
                            config["country"] = source.country
                        if hasattr(source, 'language'):
                            config["language"] = source.language
                        if hasattr(source, 'update_interval') and source.update_interval:
                            # 将timedelta转换为秒
                            config["update_interval"] = int(source.update_interval.total_seconds())
                        if hasattr(source, 'cache_ttl') and source.cache_ttl:
                            # 将timedelta转换为秒
                            config["cache_ttl"] = int(source.cache_ttl.total_seconds())
                        
                        # 添加自定义源也需要的特殊属性
                        if hasattr(source, 'status'):
                            config["status"] = source.status
                        if hasattr(source, 'need_proxy'):
                            config["need_proxy"] = source.need_proxy
                        if hasattr(source, 'proxy_fallback'):
                            config["proxy_fallback"] = source.proxy_fallback
                        if hasattr(source, 'proxy_group'):
                            config["proxy_group"] = source.proxy_group
                        
                        # 对于自定义源，记录详细日志
                        if source.id.startswith('custom-'):
                            logger.info(f"加载自定义源 {source.id} 配置: 名称={source.name}, URL={getattr(source, 'url', None)}")
                            
                        configs.append(config)
                    except Exception as e:
                        logger.error(f"解析源 {source.id} 的配置失败: {str(e)}")
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"从数据库加载源配置失败: {str(e)}")
            logger.error(traceback.format_exc())
            
        return configs 