from fastapi import APIRouter, HTTPException, Query, Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from celery.result import AsyncResult

from worker.celery_app import celery_app
from worker.tasks.news import (
    fetch_high_frequency_sources,
    fetch_medium_frequency_sources,
    fetch_low_frequency_sources,
    fetch_all_news,
    fetch_source_news
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskStatus(BaseModel):
    """任务状态模型"""
    id: str
    state: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TaskResponse(BaseModel):
    """任务响应模型"""
    id: str
    state: str


@router.get("/status/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str = Path(..., description="任务ID")):
    """
    获取任务状态
    """
    result = AsyncResult(task_id, app=celery_app)
    
    response = {
        "id": task_id,
        "state": result.state,
    }
    
    if result.state == 'SUCCESS':
        response["result"] = result.result
    elif result.state == 'FAILURE':
        response["error"] = str(result.result)
    
    return response


@router.post("/run/high-frequency", response_model=TaskResponse)
async def run_high_frequency_task():
    """
    运行高频更新任务
    """
    task = fetch_high_frequency_sources.delay()
    return {"id": task.id, "state": task.state}


@router.post("/run/medium-frequency", response_model=TaskResponse)
async def run_medium_frequency_task():
    """
    运行中频更新任务
    """
    task = fetch_medium_frequency_sources.delay()
    return {"id": task.id, "state": task.state}


@router.post("/run/low-frequency", response_model=TaskResponse)
async def run_low_frequency_task():
    """
    运行低频更新任务
    """
    task = fetch_low_frequency_sources.delay()
    return {"id": task.id, "state": task.state}


@router.post("/run/all-news", response_model=TaskResponse)
async def run_all_news_task():
    """
    运行所有新闻更新任务
    """
    task = fetch_all_news.delay()
    return {"id": task.id, "state": task.state}


@router.post("/run/source-news/{source_id}", response_model=TaskResponse)
async def run_source_news_task(source_id: str = Path(..., description="新闻源ID")):
    """
    运行指定新闻源更新任务
    """
    task = fetch_source_news.delay(source_id)
    return {"id": task.id, "state": task.state}


@router.get("/active", response_model=List[TaskStatus])
async def get_active_tasks():
    """
    获取活跃任务列表
    """
    # 注意：这个功能需要 Celery 的 Inspect 功能，可能需要额外配置
    i = celery_app.control.inspect()
    
    active_tasks = []
    
    # 获取活跃任务
    active = i.active()
    if active:
        for worker_name, tasks in active.items():
            for task in tasks:
                task_id = task.get('id')
                if task_id:
                    result = AsyncResult(task_id, app=celery_app)
                    active_tasks.append({
                        "id": task_id,
                        "state": result.state,
                        "result": None,
                        "error": None
                    })
    
    return active_tasks 