from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ProxyBase(BaseModel):
    """代理配置基本模型"""
    name: str = Field(..., description="代理名称")
    description: Optional[str] = Field(None, description="代理描述")
    protocol: str = Field("socks5", description="代理协议")
    host: str = Field(..., description="代理主机")
    port: int = Field(..., description="代理端口")
    username: Optional[str] = Field(None, description="用户名")
    password: Optional[str] = Field(None, description="密码")
    region: Optional[str] = Field(None, description="代理所在地区")
    status: str = Field("active", description="代理状态")
    priority: int = Field(0, description="优先级")
    group: str = Field("default", description="代理组")
    tags: Optional[str] = Field(None, description="标签，逗号分隔")
    health_check_url: Optional[str] = Field("https://www.baidu.com", description="健康检查URL")


class ProxyCreate(ProxyBase):
    """创建代理配置的请求模型"""
    pass


class ProxyUpdate(BaseModel):
    """更新代理配置的请求模型"""
    name: Optional[str] = Field(None, description="代理名称")
    description: Optional[str] = Field(None, description="代理描述")
    protocol: Optional[str] = Field(None, description="代理协议")
    host: Optional[str] = Field(None, description="代理主机")
    port: Optional[int] = Field(None, description="代理端口")
    username: Optional[str] = Field(None, description="用户名")
    password: Optional[str] = Field(None, description="密码")
    region: Optional[str] = Field(None, description="代理所在地区")
    status: Optional[str] = Field(None, description="代理状态")
    priority: Optional[int] = Field(None, description="优先级")
    group: Optional[str] = Field(None, description="代理组")
    tags: Optional[str] = Field(None, description="标签，逗号分隔")
    health_check_url: Optional[str] = Field(None, description="健康检查URL")


class ProxyInDB(ProxyBase):
    """数据库中的代理配置模型"""
    id: int = Field(..., description="代理ID")
    max_concurrent: Optional[int] = Field(0, description="最大并发连接数")
    success_rate: Optional[float] = Field(100.0, description="成功率")
    avg_response_time: Optional[float] = Field(0.0, description="平均响应时间")
    last_check_time: Optional[datetime] = Field(None, description="上次检查时间")
    total_requests: Optional[int] = Field(0, description="总请求次数")
    successful_requests: Optional[int] = Field(0, description="成功请求次数")
    failed_requests: Optional[int] = Field(0, description="失败请求次数")
    last_error: Optional[str] = Field(None, description="最后一次错误信息")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    
    class Config:
        from_attributes = True


class ProxyResponse(ProxyInDB):
    """代理配置响应模型"""
    pass


class ProxyListResponse(BaseModel):
    """代理配置列表响应模型"""
    items: List[ProxyResponse] = Field(..., description="代理配置列表")
    total: int = Field(..., description="总数")


class SourceProxyUpdate(BaseModel):
    """更新数据源代理设置的请求模型"""
    need_proxy: Optional[bool] = Field(None, description="是否需要代理")
    proxy_fallback: Optional[bool] = Field(None, description="代理失败时是否尝试直连")
    proxy_group: Optional[str] = Field(None, description="代理组")


class ProxyTestRequest(BaseModel):
    """测试代理的请求模型"""
    url: str = Field(..., description="测试URL")
    timeout: Optional[int] = Field(10, description="超时时间(秒)")


class ProxyTestResponse(BaseModel):
    """测试代理的响应模型"""
    success: bool = Field(..., description="是否成功")
    status_code: Optional[int] = Field(None, description="状态码")
    elapsed: Optional[float] = Field(None, description="耗时(秒)")
    error: Optional[str] = Field(None, description="错误信息") 