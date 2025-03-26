from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from app.api import deps
from app.crud import source as source_crud
from app.crud import source_stats as stats_crud
from app.schemas.monitor import (
    MonitorResponse, SourceInfo, SourceMetrics, TimeSeriesData,
    SourceHistoryResponse, SourceHistoryData, PeakTimeInfo, DayPeakInfo,
    ApiTypeMetrics, ApiTypeComparisonItem
)
from app.models.source import Source, SourceStatus
from app.models.source_stats import ApiCallType
from app.models.category import Category

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
            # 通过连接categories表和过滤slug字段实现分类过滤
            query = query.join(Source.category).filter(Category.slug == category)
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
        
        # 计算内部/外部API调用的统计信息
        api_type_metrics = {
            "internal_avg_response_time": 0.0,
            "external_avg_response_time": 0.0,
            "internal_requests": 0,
            "external_requests": 0,
            "internal_success_rate": 0.0,
            "external_success_rate": 0.0
        }
        
        internal_stats = []
        external_stats = []
        
        # 创建API类型对比数据
        api_type_comparison = []
        
        # 构建源详细信息
        source_infos = []
        for source in sources:
            # 获取内部和外部最新统计数据
            internal_latest = stats_crud.get_latest_stats(db, source.id, api_type="internal")
            external_latest = stats_crud.get_latest_stats(db, source.id, api_type="external")
            
            # 准备存储内部/外部指标
            source_api_type_metrics = {}
            
            # 获取历史聚合数据（24小时内）
            internal_history = stats_crud.get_stats_history(db, source.id, hours=24, api_type="internal")
            external_history = stats_crud.get_stats_history(db, source.id, hours=24, api_type="external")
            
            # 计算内部API的聚合指标
            if internal_latest:
                internal_stats.append(internal_latest)
                
                # 计算总请求数
                total_internal_requests = sum(stat.total_requests for stat in internal_history) if internal_history else internal_latest.total_requests
                
                # 计算加权平均响应时间
                if internal_history and len(internal_history) > 1:
                    weighted_response_time = sum(stat.avg_response_time * stat.total_requests for stat in internal_history) / max(1, sum(stat.total_requests for stat in internal_history))
                else:
                    weighted_response_time = internal_latest.avg_response_time
                
                # 计算总错误数
                total_error_count = sum(stat.error_count for stat in internal_history) if internal_history else internal_latest.error_count
                
                source_api_type_metrics["internal"] = {
                    "success_rate": internal_latest.success_rate,
                    "avg_response_time": weighted_response_time,
                    "total_requests": total_internal_requests,
                    "error_count": total_error_count
                }
            
            # 计算外部API的聚合指标
            if external_latest:
                external_stats.append(external_latest)
                
                # 计算总请求数
                total_external_requests = sum(stat.total_requests for stat in external_history) if external_history else external_latest.total_requests
                
                # 计算加权平均响应时间
                if external_history and len(external_history) > 1:
                    weighted_response_time = sum(stat.avg_response_time * stat.total_requests for stat in external_history) / max(1, sum(stat.total_requests for stat in external_history))
                else:
                    weighted_response_time = external_latest.avg_response_time
                
                # 计算总错误数
                total_error_count = sum(stat.error_count for stat in external_history) if external_history else external_latest.error_count
                
                source_api_type_metrics["external"] = {
                    "success_rate": external_latest.success_rate,
                    "avg_response_time": weighted_response_time,
                    "total_requests": total_external_requests,
                    "error_count": total_error_count
                }
            
            # 如果有内部或外部统计数据，添加到对比列表
            if internal_latest or external_latest:
                api_type_comparison.append({
                    "source_id": source.id,
                    "source_name": source.name,
                    "internal": source_api_type_metrics.get("internal"),
                    "external": source_api_type_metrics.get("external")
                })
            
            # 使用合并的统计信息或内部统计信息
            latest_stats = internal_latest or stats_crud.get_latest_stats(db, source.id)
            
            # 获取历史统计数据以计算聚合指标
            all_stats_history = stats_crud.get_stats_history(db, source.id, hours=24)
            
            # 计算聚合指标
            if all_stats_history:
                # 计算总请求数
                total_requests = sum(stat.total_requests for stat in all_stats_history)
                
                # 计算加权平均响应时间
                if total_requests > 0:
                    weighted_avg_response_time = sum(stat.avg_response_time * stat.total_requests for stat in all_stats_history) / total_requests
                else:
                    weighted_avg_response_time = latest_stats.avg_response_time if latest_stats else 0.0
                
                # 计算总错误数
                total_error_count = sum(stat.error_count for stat in all_stats_history)
                
                # 计算加权成功率
                if total_requests > 0:
                    weighted_success_rate = sum(stat.success_rate * stat.total_requests for stat in all_stats_history) / total_requests
                else:
                    weighted_success_rate = latest_stats.success_rate if latest_stats else 0.0
                    
                # 计算总新闻数
                total_news_count = sum(stat.news_count for stat in all_stats_history)
            else:
                # 如果没有历史数据，使用最新的统计信息
                total_requests = latest_stats.total_requests if latest_stats else 0
                weighted_avg_response_time = latest_stats.avg_response_time if latest_stats else 0.0
                total_error_count = latest_stats.error_count if latest_stats else 0
                weighted_success_rate = latest_stats.success_rate if latest_stats else 0.0
                total_news_count = latest_stats.news_count if latest_stats else 0
            
            metrics = SourceMetrics(
                success_rate=weighted_success_rate,
                avg_response_time=weighted_avg_response_time,
                total_requests=total_requests,
                error_count=total_error_count,
                last_update=source.last_updated,
                last_error=source.last_error,
                news_count=total_news_count
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
                metrics=metrics,
                api_type_metrics=source_api_type_metrics
            ))
        
        # 计算内部/外部API调用的平均响应时间和请求总数
        if internal_stats:
            # 获取所有数据源的24小时内内部API调用历史
            all_internal_history = []
            for source in sources:
                source_history = stats_crud.get_stats_history(db, source.id, hours=24, api_type="internal")
                if source_history:
                    all_internal_history.extend(source_history)
            
            # 计算总请求数
            api_type_metrics["internal_requests"] = sum(stat.total_requests for stat in all_internal_history) if all_internal_history else sum(s.total_requests for s in internal_stats)
            
            # 计算加权平均响应时间
            if all_internal_history:
                total_requests = sum(stat.total_requests for stat in all_internal_history)
                if total_requests > 0:
                    api_type_metrics["internal_avg_response_time"] = sum(stat.avg_response_time * stat.total_requests for stat in all_internal_history) / total_requests
                else:
                    api_type_metrics["internal_avg_response_time"] = sum(s.avg_response_time for s in internal_stats) / len(internal_stats)
            else:
                api_type_metrics["internal_avg_response_time"] = sum(s.avg_response_time for s in internal_stats) / len(internal_stats)
            
            # 计算加权成功率
            if api_type_metrics["internal_requests"] > 0:
                total_success = sum((stat.success_rate * stat.total_requests) for stat in all_internal_history) if all_internal_history else sum(s.success_rate * s.total_requests for s in internal_stats)
                api_type_metrics["internal_success_rate"] = total_success / api_type_metrics["internal_requests"]
            else:
                api_type_metrics["internal_success_rate"] = 0
        
        if external_stats:
            # 获取所有数据源的24小时内外部API调用历史
            all_external_history = []
            for source in sources:
                source_history = stats_crud.get_stats_history(db, source.id, hours=24, api_type="external")
                if source_history:
                    all_external_history.extend(source_history)
            
            # 计算总请求数
            api_type_metrics["external_requests"] = sum(stat.total_requests for stat in all_external_history) if all_external_history else sum(s.total_requests for s in external_stats)
            
            # 计算加权平均响应时间
            if all_external_history:
                total_requests = sum(stat.total_requests for stat in all_external_history)
                if total_requests > 0:
                    api_type_metrics["external_avg_response_time"] = sum(stat.avg_response_time * stat.total_requests for stat in all_external_history) / total_requests
                else:
                    api_type_metrics["external_avg_response_time"] = sum(s.avg_response_time for s in external_stats) / len(external_stats)
            else:
                api_type_metrics["external_avg_response_time"] = sum(s.avg_response_time for s in external_stats) / len(external_stats)
            
            # 计算加权成功率
            if api_type_metrics["external_requests"] > 0:
                total_success = sum((stat.success_rate * stat.total_requests) for stat in all_external_history) if all_external_history else sum(s.success_rate * s.total_requests for s in external_stats)
                api_type_metrics["external_success_rate"] = total_success / api_type_metrics["external_requests"]
            else:
                api_type_metrics["external_success_rate"] = 0
            
        # 计算总体平均响应时间
        all_stats = [stats_crud.get_latest_stats(db, s.id) for s in sources]
        valid_stats = [s for s in all_stats if s is not None]
        avg_response_time = (
            sum(s.avg_response_time for s in valid_stats) / len(valid_stats)
            if valid_stats else 0.0
        )
        
        return MonitorResponse(
            total_sources=total_sources,
            active_sources=active_sources,
            error_sources=error_sources,
            warning_sources=warning_sources,
            inactive_sources=inactive_sources,
            avg_response_time=avg_response_time,
            historical_data=historical_data,
            sources=source_infos,
            api_type_metrics=api_type_metrics,
            api_type_comparison=api_type_comparison
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch monitoring data: {str(e)}"
        )

@router.get("/sources/{source_id}/history", response_model=SourceHistoryResponse)
def get_source_history(
    source_id: str,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(deps.get_db)
):
    """
    获取特定源的历史统计数据和访问高峰期分析
    
    Args:
        source_id: 新闻源ID
        hours: 查询历史数据的小时数 (1-168小时)
        
    Returns:
        包含历史数据、高峰期和其他统计信息的JSON对象
    """
    # 获取源及其历史统计数据
    source = source_crud.get_source(db, source_id)
    if not source:
        raise HTTPException(
            status_code=404,
            detail=f"Source with ID {source_id} not found"
        )
    
    # 获取历史统计数据
    stats_history = stats_crud.get_stats_history(db, source_id, hours=hours)
    if not stats_history:
        return {
            "history": [],
            "peak_times": [],
            "peak_times_by_day": [],
            "highest_response_times": []
        }
    
    # 准备历史数据
    history = []
    for stat in stats_history:
        history.append(SourceHistoryData(
            timestamp=stat.created_at,
            success_rate=stat.success_rate,
            avg_response_time=stat.avg_response_time,
            total_requests=stat.total_requests,
            error_count=stat.error_count,
            news_count=stat.news_count
        ))
    
    # 分析访问高峰期 - 按绝对时间点
    request_counts = {}
    for i in range(len(history) - 1):
        # 计算每个时间点的请求增量
        curr = history[i]
        next_stat = history[i+1]
        
        # 防止数据异常导致的负值
        request_diff = max(0, next_stat.total_requests - curr.total_requests)
        if request_diff > 0:
            timestamp = next_stat.timestamp
            request_counts[timestamp] = request_diff
    
    # 找出前3个高峰期
    peak_times = []
    if request_counts:
        sorted_counts = sorted(request_counts.items(), key=lambda x: x[1], reverse=True)
        peak_times = [PeakTimeInfo(timestamp=ts, count=count) for ts, count in sorted_counts[:3]]
    
    # 按天和小时分析高峰期
    day_hour_counts = {}
    for timestamp, count in request_counts.items():
        day_name = timestamp.strftime('%A')  # 星期几
        hour = timestamp.hour
        
        key = (day_name, hour)
        if key not in day_hour_counts:
            day_hour_counts[key] = 0
        day_hour_counts[key] += count
    
    # 找出每天的高峰小时
    days = {}
    for (day, hour), count in day_hour_counts.items():
        if day not in days or count > days[day]["count"]:
            days[day] = {"hour": hour, "count": count}
    
    peak_times_by_day = [DayPeakInfo(day=day, hour=data["hour"], count=data["count"]) 
                          for day, data in days.items()]
    
    # 找出响应时间最高的几个时间点
    sorted_by_response_time = sorted(history, key=lambda x: x.avg_response_time, reverse=True)
    highest_response_times = sorted_by_response_time[:3]
    
    return SourceHistoryResponse(
        history=history,
        peak_times=peak_times,
        peak_times_by_day=peak_times_by_day,
        highest_response_times=highest_response_times
    ) 