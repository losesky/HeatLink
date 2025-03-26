from typing import List, Optional, Dict, Any
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
    news_count: Optional[int] = 0

class ApiTypeMetricsDetail(BaseModel):
    """某个API类型（内部或外部）的具体指标"""
    success_rate: float
    avg_response_time: float
    total_requests: int
    error_count: int

class ApiTypeMetrics(BaseModel):
    """内部/外部API调用统计指标"""
    internal_avg_response_time: float
    external_avg_response_time: float
    internal_requests: int
    external_requests: int
    internal_success_rate: float
    external_success_rate: float

class ApiTypeComparisonItem(BaseModel):
    """API类型比较项，用于比较不同源的内部/外部API性能"""
    source_id: str
    source_name: str
    internal: Optional[Dict[str, Any]] = None
    external: Optional[Dict[str, Any]] = None

class SourceInfo(BaseModel):
    """新闻源详细信息"""
    id: str
    name: str
    description: str
    category: Optional[str] = None
    status: str
    metrics: SourceMetrics
    api_type_metrics: Optional[Dict[str, Dict[str, Any]]] = None

class TimeSeriesData(BaseModel):
    """时间序列数据点"""
    timestamp: datetime
    value: float

class SourceHistoryData(BaseModel):
    """源历史统计数据点"""
    timestamp: datetime
    success_rate: float
    avg_response_time: float
    total_requests: int
    error_count: int
    news_count: int = 0

class PeakTimeInfo(BaseModel):
    """访问高峰期信息"""
    timestamp: datetime
    count: int

class DayPeakInfo(BaseModel):
    """每日访问高峰期信息"""
    day: str
    hour: int
    count: int

class SourceHistoryResponse(BaseModel):
    """源历史数据响应"""
    history: List[SourceHistoryData]
    peak_times: List[PeakTimeInfo]
    peak_times_by_day: List[DayPeakInfo]
    highest_response_times: List[SourceHistoryData]

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
    api_type_metrics: Optional[ApiTypeMetrics] = None
    api_type_comparison: Optional[List[Dict[str, Any]]] = None 