from abc import abstractmethod
from typing import List, Dict, Any, Optional

# 为了避免循环导入，我们使用TYPE_CHECKING
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # 仅类型检查时导入
    from worker.sources.base import NewsItemModel


class NewsSourceInterface:
    """
    新闻源接口
    所有新闻源适配器必须实现这个接口
    """
    
    @property
    @abstractmethod
    def source_id(self) -> str:
        """获取源ID"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """获取源名称"""
        pass
    
    @property
    @abstractmethod
    def category(self) -> str:
        """获取源分类"""
        pass
    
    @property
    @abstractmethod
    def update_interval(self) -> int:
        """获取更新间隔"""
        pass
    
    @abstractmethod
    async def get_news(self) -> List["NewsItemModel"]:
        """
        获取新闻
        
        Returns:
            新闻列表
        """
        pass
    
    @abstractmethod
    def should_update(self) -> bool:
        """
        判断是否应该更新
        
        Returns:
            是否应该更新
        """
        pass
    
    @abstractmethod
    def update_metrics(self, news_count: int, success: bool = True, error: Optional[Exception] = None) -> None:
        """
        更新性能指标
        
        Args:
            news_count: 获取的新闻数量
            success: 是否成功
            error: 错误信息
        """
        pass 