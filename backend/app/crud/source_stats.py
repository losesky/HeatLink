from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.source_stats import SourceStats
from app.models.source import Source, SourceStatus
from datetime import datetime, timedelta

def create_source_stats(
    db: Session,
    source_id: str,
    success_rate: float,
    avg_response_time: float,
    total_requests: int,
    error_count: int
) -> SourceStats:
    """创建新的源统计数据"""
    db_stats = SourceStats(
        source_id=source_id,
        success_rate=success_rate,
        avg_response_time=avg_response_time,
        total_requests=total_requests,
        error_count=error_count
    )
    db.add(db_stats)
    db.commit()
    db.refresh(db_stats)
    return db_stats

def get_latest_stats(db: Session, source_id: str) -> Optional[SourceStats]:
    """获取最新的源统计数据"""
    return db.query(SourceStats).filter(
        SourceStats.source_id == source_id
    ).order_by(SourceStats.created_at.desc()).first()

def get_stats_history(
    db: Session,
    source_id: str,
    hours: int = 24
) -> List[SourceStats]:
    """获取历史统计数据"""
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    return db.query(SourceStats).filter(
        SourceStats.source_id == source_id,
        SourceStats.created_at >= cutoff_time
    ).order_by(SourceStats.created_at.asc()).all()

def update_source_status(
    db: Session,
    source_id: str,
    success_rate: float,
    avg_response_time: float,
    total_requests: int,
    error_count: int,
    last_error: Optional[str] = None
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
    
    source.last_update = datetime.utcnow()
    source.last_error = last_error
    
    # 创建新的统计数据
    create_source_stats(
        db=db,
        source_id=source_id,
        success_rate=success_rate,
        avg_response_time=avg_response_time,
        total_requests=total_requests,
        error_count=error_count
    )
    
    db.commit()
    db.refresh(source)
    return source 