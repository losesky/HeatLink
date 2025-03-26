from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.source_stats import SourceStats, ApiCallType
from app.models.source import Source, SourceStatus
from datetime import datetime, timedelta
from sqlalchemy.types import String

def create_source_stats(
    db: Session,
    source_id: str,
    success_rate: float,
    avg_response_time: float,
    total_requests: int,
    error_count: int,
    news_count: int = 0,
    last_response_time: float = 0.0,
    api_type: str = "internal"  # 默认为内部调用
) -> SourceStats:
    """创建新的源统计数据"""
    # 确保api_type是小写，然后转换为正确的枚举值
    api_type = api_type.lower()
    
    # 根据api_type字符串选择正确的枚举实例
    if api_type == "internal":
        enum_api_type = ApiCallType.internal
    elif api_type == "external":
        enum_api_type = ApiCallType.external
    else:
        # 默认使用内部类型
        enum_api_type = ApiCallType.internal
    
    db_stats = SourceStats(
        source_id=source_id,
        success_rate=success_rate,
        avg_response_time=avg_response_time,
        total_requests=total_requests,
        error_count=error_count,
        news_count=news_count,
        last_response_time=last_response_time,
        api_type=enum_api_type
    )
    db.add(db_stats)
    db.commit()
    db.refresh(db_stats)
    return db_stats

def get_latest_stats(db: Session, source_id: str, api_type: Optional[str] = None) -> Optional[SourceStats]:
    """获取最新的源统计数据，可以按api_type过滤"""
    query = db.query(SourceStats).filter(SourceStats.source_id == source_id)
    
    if api_type:
        query = query.filter(SourceStats.api_type.cast(String) == api_type)
        
    return query.order_by(SourceStats.created_at.desc()).first()

def get_stats_history(
    db: Session,
    source_id: str,
    hours: int = 24,
    api_type: Optional[str] = None
) -> List[SourceStats]:
    """获取历史统计数据，可以按api_type过滤"""
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    query = db.query(SourceStats).filter(
        SourceStats.source_id == source_id,
        SourceStats.created_at >= cutoff_time
    )
    
    if api_type:
        query = query.filter(SourceStats.api_type.cast(String) == api_type)
        
    return query.order_by(SourceStats.created_at.asc()).all()

def update_source_status(
    db: Session,
    source_id: str,
    success_rate: float,
    avg_response_time: float,
    total_requests: int,
    error_count: int,
    last_error: Optional[str] = None,
    news_count: int = 0,
    last_response_time: float = 0.0,
    api_type: str = "internal"  # 默认为内部调用
) -> Source:
    """更新源状态和统计数据"""
    # 更新源状态
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise ValueError(f"Source {source_id} not found")
    
    # 根据错误率确定状态
    if error_count > 0:
        if error_count / total_requests > 0.5:
            source.status = SourceStatus.ERROR
        else:
            source.status = SourceStatus.WARNING
    else:
        source.status = SourceStatus.ACTIVE
    
    source.last_updated = datetime.utcnow()
    source.last_error = last_error
    
    # 创建新的统计数据
    create_source_stats(
        db=db,
        source_id=source_id,
        success_rate=success_rate,
        avg_response_time=avg_response_time,
        total_requests=total_requests,
        error_count=error_count,
        news_count=news_count,
        last_response_time=last_response_time,
        api_type=api_type
    )
    
    db.commit()
    db.refresh(source)
    return source 