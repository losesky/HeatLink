from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

class SourceMetrics(BaseModel):
    """单个新闻源的性能指标"""
    success_rate: float
    avg_response_time: float
    total_requests: int
    error_count: int
    last_update: Optional[datetime]
    last_error: Optional[str]

class SourceInfo(BaseModel):
    """新闻源详细信息"""
    id: str
    name: str
    description: str
    category: Optional[str] = None
    status: str
    metrics: SourceMetrics

class TimeSeriesData(BaseModel):
    """时间序列数据点"""
    timestamp: datetime
    value: float

class MonitorResponse(BaseModel):
    """监控数据响应"""
    total_sources: int
    active_sources: int
    error_sources: int
    warning_sources: int
    inactive_sources: int
    avg_response_time: float
    historical_data: List[TimeSeriesData]
    sources: List[SourceInfo] 