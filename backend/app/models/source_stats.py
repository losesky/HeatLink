from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, String, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.db.session import Base
from datetime import datetime
from enum import Enum

class ApiCallType(str, Enum):
    internal = "internal"  # 内部调度任务访问
    external = "external"  # 外部API访问

class SourceStats(Base):
    """
    新闻源统计数据模型
    用于记录每个新闻源的性能指标和统计信息
    """
    __tablename__ = "source_stats"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(String, ForeignKey("sources.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # 性能指标
    success_rate = Column(Float, default=0.0)  # 成功率
    avg_response_time = Column(Float, default=0.0)  # 平均响应时间（毫秒）
    total_requests = Column(Integer, default=0)  # 总请求数
    error_count = Column(Integer, default=0)  # 错误数
    news_count = Column(Integer, default=0)  # 新闻数量
    last_response_time = Column(Float, default=0.0)  # 最后一次响应时间（毫秒）
    api_type = Column(SQLEnum(ApiCallType), default=ApiCallType.internal, nullable=False)  # API调用类型
    
    # 关联关系
    source = relationship("Source", back_populates="stats") 