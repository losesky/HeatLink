from typing import List, Optional, Dict, Any
import time
import logging
import asyncio
import os
from fastapi import APIRouter, Depends, HTTPException, Query, Path, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from app.db.session import get_db
from app.api.deps import get_current_active_superuser, get_current_active_user
from app.models.user import User
from app.models.proxy import ProxyConfig, ProxyStatus
from app.models.source import Source
from app.schemas.proxy import (
    ProxyCreate, ProxyUpdate, ProxyResponse, ProxyListResponse,
    SourceProxyUpdate, ProxyTestRequest, ProxyTestResponse
)
from app.core.config import settings

# 导入代理管理器
from worker.utils.proxy_manager import proxy_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# 添加代理域名列表的请求模型
class ProxyDomainsUpdate(BaseModel):
    domains: List[str]
    
# 添加响应模型
class ProxyDomainsResponse(BaseModel):
    domains: List[str]

# 添加状态响应模型
class StatusResponse(BaseModel):
    status: str
    message: str

@router.get("/", response_model=ProxyListResponse)
async def list_proxies(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    group: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    获取代理配置列表
    """
    # 构建查询
    query = db.query(ProxyConfig)
    
    # 应用筛选条件
    if status:
        query = query.filter(ProxyConfig.status == status.upper())
    
    if group:
        query = query.filter(ProxyConfig.group == group)
    
    if search:
        query = query.filter(
            ProxyConfig.name.ilike(f"%{search}%") |
            ProxyConfig.description.ilike(f"%{search}%") |
            ProxyConfig.host.ilike(f"%{search}%")
        )
    
    # 获取总数
    total = query.count()
    
    # 应用分页
    query = query.order_by(ProxyConfig.priority.desc()).offset(skip).limit(limit)
    
    return {
        "items": query.all(),
        "total": total
    }


@router.post("/", response_model=ProxyResponse)
async def create_proxy(
    proxy: ProxyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    创建新的代理配置
    """
    # 检查是否已存在相同配置的代理
    existing_proxy = db.query(ProxyConfig).filter(
        ProxyConfig.host == proxy.host,
        ProxyConfig.port == proxy.port,
        ProxyConfig.protocol == proxy.protocol.upper()
    ).first()
    
    if existing_proxy:
        raise HTTPException(
            status_code=400,
            detail=f"代理 {proxy.host}:{proxy.port} 已存在"
        )
    
    # 创建新代理
    db_proxy = ProxyConfig(
        name=proxy.name,
        description=proxy.description,
        protocol=proxy.protocol.upper(),
        host=proxy.host,
        port=proxy.port,
        username=proxy.username,
        password=proxy.password,
        region=proxy.region,
        status=proxy.status.upper(),
        priority=proxy.priority,
        group=proxy.group,
        tags=proxy.tags,
        health_check_url=proxy.health_check_url
    )
    
    db.add(db_proxy)
    db.commit()
    db.refresh(db_proxy)
    
    # 刷新代理管理器
    await proxy_manager.refresh_proxies()
    
    return db_proxy


@router.get("/{proxy_id}", response_model=ProxyResponse)
async def get_proxy(
    proxy_id: int = Path(..., description="代理ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    获取代理配置详情
    """
    proxy = db.query(ProxyConfig).filter(ProxyConfig.id == proxy_id).first()
    if not proxy:
        raise HTTPException(
            status_code=404,
            detail=f"代理 {proxy_id} 不存在"
        )
    
    return proxy


@router.put("/{proxy_id}", response_model=ProxyResponse)
async def update_proxy(
    proxy_update: ProxyUpdate,
    proxy_id: int = Path(..., description="代理ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    更新代理配置
    """
    proxy = db.query(ProxyConfig).filter(ProxyConfig.id == proxy_id).first()
    if not proxy:
        raise HTTPException(
            status_code=404,
            detail=f"代理 {proxy_id} 不存在"
        )
    
    # 更新字段
    for field, value in proxy_update.dict(exclude_unset=True).items():
        if field == "protocol" and value is not None:
            setattr(proxy, field, value.upper())
        elif field == "status" and value is not None:
            setattr(proxy, field, value.upper())
        else:
            setattr(proxy, field, value)
    
    db.commit()
    db.refresh(proxy)
    
    # 刷新代理管理器
    await proxy_manager.refresh_proxies()
    
    return proxy


@router.delete("/{proxy_id}")
async def delete_proxy(
    proxy_id: int = Path(..., description="代理ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    删除代理配置
    """
    proxy = db.query(ProxyConfig).filter(ProxyConfig.id == proxy_id).first()
    if not proxy:
        raise HTTPException(
            status_code=404,
            detail=f"代理 {proxy_id} 不存在"
        )
    
    # 检查是否有数据源正在使用该代理组
    using_sources = db.query(Source).filter(
        Source.need_proxy == True,
        Source.proxy_group == proxy.group
    ).count()
    
    if using_sources > 0 and db.query(ProxyConfig).filter(
        ProxyConfig.group == proxy.group,
        ProxyConfig.id != proxy_id
    ).count() == 0:
        # 如果这是该组的最后一个代理，且有数据源正在使用，则不允许删除
        raise HTTPException(
            status_code=400,
            detail=f"无法删除 {proxy.name}。该代理是代理组 {proxy.group} 的最后一个代理，且有 {using_sources} 个数据源正在使用该代理组。"
        )
    
    db.delete(proxy)
    db.commit()
    
    # 刷新代理管理器
    await proxy_manager.refresh_proxies()
    
    return {"message": f"代理 {proxy.name} 已删除"}


@router.post("/{proxy_id}/check", response_model=ProxyTestResponse)
async def check_proxy(
    proxy_id: int = Path(..., description="代理ID"),
    test_request: ProxyTestRequest = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    检查代理状态
    """
    proxy = db.query(ProxyConfig).filter(ProxyConfig.id == proxy_id).first()
    if not proxy:
        raise HTTPException(
            status_code=404,
            detail=f"代理 {proxy_id} 不存在"
        )
    
    # 默认测试URL
    test_url = "https://www.baidu.com"
    timeout = 10
    
    if test_request:
        test_url = test_request.url
        timeout = test_request.timeout
    
    # 获取代理URL
    proxy_url = proxy.get_proxy_url()
    
    # 测试代理
    import aiohttp
    
    start_time = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                test_url,
                proxy=proxy_url,
                timeout=timeout
            ) as response:
                elapsed = time.time() - start_time
                
                # 更新代理状态
                proxy.last_check_time = func.now()
                proxy.avg_response_time = elapsed
                
                if response.status == 200:
                    proxy.status = ProxyStatus.ACTIVE
                    proxy.last_error = None
                    db.commit()
                    
                    return {
                        "success": True,
                        "status_code": response.status,
                        "elapsed": elapsed,
                        "error": None
                    }
                else:
                    proxy.status = ProxyStatus.ERROR
                    proxy.last_error = f"健康检查返回非200状态码: {response.status}"
                    db.commit()
                    
                    return {
                        "success": False,
                        "status_code": response.status,
                        "elapsed": elapsed,
                        "error": f"返回状态码 {response.status}"
                    }
    except Exception as e:
        elapsed = time.time() - start_time
        
        # 更新代理状态
        proxy.status = ProxyStatus.ERROR
        proxy.last_error = str(e)
        proxy.last_check_time = func.now()
        db.commit()
        
        return {
            "success": False,
            "status_code": None,
            "elapsed": elapsed,
            "error": str(e)
        }


@router.post("/check-all")
async def check_all_proxies(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    检查所有代理状态（后台任务）
    """
    # 将健康检查添加为后台任务
    background_tasks.add_task(proxy_manager.check_proxy_health)
    
    return {"message": "已启动所有代理的健康检查，请稍后查看结果"}


@router.put("/source/{source_id}/proxy", response_model=Dict[str, Any])
async def update_source_proxy_settings(
    proxy_settings: SourceProxyUpdate,
    source_id: str = Path(..., description="数据源ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    更新数据源的代理设置
    """
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(
            status_code=404,
            detail=f"数据源 {source_id} 不存在"
        )
    
    # 更新字段
    update_fields = {}
    for field, value in proxy_settings.dict(exclude_unset=True).items():
        setattr(source, field, value)
        update_fields[field] = value
    
    db.commit()
    
    # 如果启用了代理，检查指定的代理组是否存在
    if proxy_settings.need_proxy and proxy_settings.proxy_group:
        proxy_group_exists = db.query(ProxyConfig).filter(
            ProxyConfig.group == proxy_settings.proxy_group,
            ProxyConfig.status == ProxyStatus.ACTIVE
        ).first() is not None
        
        if not proxy_group_exists:
            return {
                "message": f"数据源 {source.name} 的代理设置已更新，但代理组 '{proxy_settings.proxy_group}' 中没有活跃的代理。",
                "warning": True,
                "updated_fields": update_fields
            }
    
    return {
        "message": f"数据源 {source.name} 的代理设置已更新",
        "warning": False,
        "updated_fields": update_fields
    }


@router.get("/domains", response_model=ProxyDomainsResponse)
async def get_proxy_domains(
    current_user: User = Depends(get_current_active_user)
):
    """
    获取当前需要代理的域名列表
    """
    return {"domains": settings.proxy_domains}


@router.put("/domains", response_model=StatusResponse)
async def update_proxy_domains(
    domains_update: ProxyDomainsUpdate,
    current_user: User = Depends(get_current_active_superuser)
):
    """
    更新需要代理的域名列表
    
    此操作会更新.env文件中的PROXY_REQUIRED_DOMAINS配置，并更新运行时设置
    需要重启服务才能完全生效
    """
    try:
        # 去重并排序域名
        unique_domains = sorted(set(domains_update.domains))
        
        # 构建新的.env内容
        env_path = ".env"
        new_content = []
        domains_line_added = False
        
        # 读取现有.env文件并更新域名行
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    # 如果找到PROXY_REQUIRED_DOMAINS行，替换它
                    if line.strip().startswith("PROXY_REQUIRED_DOMAINS="):
                        new_content.append(f"PROXY_REQUIRED_DOMAINS={','.join(unique_domains)}\n")
                        domains_line_added = True
                    else:
                        new_content.append(line)
        
        # 如果.env文件中没有PROXY_REQUIRED_DOMAINS行，添加它
        if not domains_line_added:
            new_content.append(f"\n# Proxy settings\nPROXY_REQUIRED_DOMAINS={','.join(unique_domains)}\n")
        
        # 写回.env文件
        with open(env_path, "w") as f:
            f.writelines(new_content)
        
        # 更新运行时设置
        settings.PROXY_REQUIRED_DOMAINS = ','.join(unique_domains)
        
        return {
            "status": "success",
            "message": "代理域名列表已更新。服务器重启后将完全生效。"
        }
    except Exception as e:
        logger.error(f"更新代理域名列表失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"更新代理域名列表失败: {str(e)}"
        ) 