from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from app.api import deps
from app.crud import source as source_crud
from app.crud import source_stats as stats_crud
from app.schemas.monitor import MonitorResponse, SourceInfo, SourceMetrics, TimeSeriesData
from app.models.source import Source, SourceStatus

router = APIRouter()

@router.get("/sources", response_model=MonitorResponse)
def get_source_monitor_data(
    status: Optional[SourceStatus] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(deps.get_db)
):
    """
    获取新闻源监控数据
    """
    try:
        # 构建查询
        query = db.query(Source)
        
        # 应用过滤条件
        if status:
            query = query.filter(Source.status == status)
        if category:
            query = query.filter(Source.category == category)
        if search:
            query = query.filter(
                (Source.name.ilike(f"%{search}%")) |
                (Source.description.ilike(f"%{search}%"))
            )
        
        # 获取所有匹配的源
        sources = query.all()
        
        # 计算总体统计信息
        total_sources = len(sources)
        active_sources = sum(1 for s in sources if s.status == SourceStatus.ACTIVE)
        error_sources = sum(1 for s in sources if s.status == SourceStatus.ERROR)
        warning_sources = sum(1 for s in sources if s.status == SourceStatus.WARNING)
        inactive_sources = sum(1 for s in sources if s.status == SourceStatus.INACTIVE)
        
        # 获取历史响应时间数据
        historical_data = []
        for source in sources:
            stats_history = stats_crud.get_stats_history(db, source.id)
            if stats_history:
                # 按小时聚合数据
                hourly_data = {}
                for stat in stats_history:
                    hour = stat.created_at.replace(minute=0, second=0, microsecond=0)
                    if hour not in hourly_data:
                        hourly_data[hour] = []
                    hourly_data[hour].append(stat.avg_response_time)
                
                # 计算每小时的平均值
                for hour, times in hourly_data.items():
                    historical_data.append(TimeSeriesData(
                        timestamp=hour,
                        value=sum(times) / len(times)
                    ))
        
        # 计算总体平均响应时间
        all_stats = [stats_crud.get_latest_stats(db, s.id) for s in sources]
        valid_stats = [s for s in all_stats if s is not None]
        avg_response_time = (
            sum(s.avg_response_time for s in valid_stats) / len(valid_stats)
            if valid_stats else 0.0
        )
        
        # 构建源详细信息
        source_infos = []
        for source in sources:
            latest_stats = stats_crud.get_latest_stats(db, source.id)
            metrics = SourceMetrics(
                success_rate=latest_stats.success_rate if latest_stats else 0.0,
                avg_response_time=latest_stats.avg_response_time if latest_stats else 0.0,
                total_requests=latest_stats.total_requests if latest_stats else 0,
                error_count=latest_stats.error_count if latest_stats else 0,
                last_update=source.last_update,
                last_error=source.last_error
            )
            
            # 修复 category 字段类型问题
            category_name = None
            if source.category:
                # 如果 category 是对象，获取其名称；如果是 ID，直接使用
                category_name = source.category.name if hasattr(source.category, 'name') else str(source.category)
            
            source_infos.append(SourceInfo(
                id=source.id,
                name=source.name,
                description=source.description,
                category=category_name,  # 使用获取的名称
                status=source.status,
                metrics=metrics
            ))
        
        return MonitorResponse(
            total_sources=total_sources,
            active_sources=active_sources,
            error_sources=error_sources,
            warning_sources=warning_sources,
            inactive_sources=inactive_sources,
            avg_response_time=avg_response_time,
            historical_data=historical_data,
            sources=source_infos
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch monitoring data: {str(e)}"
        ) 