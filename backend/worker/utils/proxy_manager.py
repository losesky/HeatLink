import time
import random
import logging
import asyncio
import contextlib
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime, timedelta

import aiohttp
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.proxy import ProxyConfig, ProxyStatus
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


class ProxyManager:
    """
    代理管理器类
    负责管理代理池，提供代理选择、监控和故障处理功能
    """
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ProxyManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, refresh_interval: int = 300):
        """
        初始化代理管理器
        
        Args:
            refresh_interval: 代理列表刷新间隔(秒)
        """
        if self._initialized:
            return
            
        self.refresh_interval = refresh_interval
        
        # 代理缓存
        self._proxies = {}  # 所有代理 {id: proxy_config}
        self._active_proxies = {}  # 活跃代理 {group: [proxy_config, ...]}
        self._proxy_status = {}  # 代理状态 {proxy_url: {"success": 0, "failure": 0, "last_used": timestamp}}
        
        # 锁，用于并发控制
        self._locks = {}  # {proxy_id: asyncio.Lock()}
        
        # 缓存时间戳
        self._last_refresh = 0
        self._refreshing = False
        
        # 初始化标记
        self._initialized = True
    
    async def initialize(self):
        """初始化代理池，加载代理配置"""
        await self.refresh_proxies()
    
    async def refresh_proxies(self) -> bool:
        """
        从数据库刷新代理列表
        
        Returns:
            bool: 是否刷新成功
        """
        # 防止并发刷新
        if self._refreshing:
            return False
            
        try:
            self._refreshing = True
            now = time.time()
            
            # 如果距离上次刷新时间不够长，则跳过
            if now - self._last_refresh < self.refresh_interval:
                return False
            
            logger.info("正在刷新代理列表...")
            # 使用同步方式查询数据库
            db = SessionLocal()
            try:
                proxies = db.query(ProxyConfig).all()
                
                # 重置缓存
                self._proxies = {}
                self._active_proxies = {}
                
                # 更新缓存
                for proxy in proxies:
                    self._proxies[proxy.id] = proxy
                    
                    # 只添加活跃的代理
                    if proxy.status == ProxyStatus.ACTIVE:
                        group = proxy.group or "default"
                        if group not in self._active_proxies:
                            self._active_proxies[group] = []
                        self._active_proxies[group].append(proxy)
                
                # 按优先级排序
                for group in self._active_proxies:
                    self._active_proxies[group] = sorted(
                        self._active_proxies[group], 
                        key=lambda x: (x.priority, x.success_rate), 
                        reverse=True
                    )
                
                self._last_refresh = now
                logger.info(f"代理列表刷新完成，共加载 {len(self._proxies)} 个代理，{len(self._active_proxies)} 个代理组")
                return True
            finally:
                db.close()
        except Exception as e:
            logger.error(f"刷新代理列表出错: {e}")
            return False
        finally:
            self._refreshing = False
    
    async def get_proxy(self, source_id: str = None, group: str = "default") -> Optional[Dict[str, Any]]:
        """
        获取适合当前数据源的代理
        
        Args:
            source_id: 数据源ID，用于特定数据源的代理选择
            group: 代理组名称
            
        Returns:
            Optional[Dict[str, Any]]: 代理配置
        """
        # 确保代理列表已刷新
        now = time.time()
        if now - self._last_refresh > self.refresh_interval:
            await self.refresh_proxies()
        
        # 如果没有可用代理，返回None
        if not self._active_proxies or (group not in self._active_proxies and "default" not in self._active_proxies):
            # 如果请求的组不存在但default组存在，降级使用default组
            if "default" in self._active_proxies:
                group = "default"
                logger.warning(f"请求的代理组 '{group}' 不存在，降级使用default组")
            else:
                logger.warning(f"没有可用的代理 (组: {group})")
                return None
        
        # 获取指定组的代理列表
        proxies = self._active_proxies.get(group, [])
        if not proxies:
            logger.warning(f"代理组 '{group}' 中没有可用代理")
            return None
        
        # 选择代理
        # 简单策略: 80%概率选择高优先级代理，20%概率随机选择
        if random.random() < 0.8 and len(proxies) > 1:
            # 优先选择高优先级代理
            selected_proxy = proxies[0]
        else:
            # 随机选择
            selected_proxy = random.choice(proxies)
        
        # 返回代理配置
        return {
            "id": selected_proxy.id,
            "protocol": selected_proxy.protocol.lower(),
            "host": selected_proxy.host,
            "port": selected_proxy.port,
            "username": selected_proxy.username,
            "password": selected_proxy.password,
            "url": selected_proxy.get_proxy_url()
        }
    
    async def report_proxy_status(self, proxy_id: int, success: bool, response_time: float = None):
        """
        报告代理使用状态
        
        Args:
            proxy_id: 代理ID
            success: 是否成功
            response_time: 响应时间(秒)
        """
        if proxy_id not in self._proxies:
            logger.warning(f"报告状态的代理不存在: {proxy_id}")
            return
            
        # 防止并发更新，使用锁
        if proxy_id not in self._locks:
            self._locks[proxy_id] = asyncio.Lock()
            
        async with self._locks[proxy_id]:
            try:
                # 使用同步数据库访问
                db = SessionLocal()
                try:
                    proxy = db.query(ProxyConfig).filter(ProxyConfig.id == proxy_id).first()
                    if not proxy:
                        logger.warning(f"代理不存在: {proxy_id}")
                        return
                    
                    # 更新统计信息
                    proxy.total_requests += 1
                    if success:
                        proxy.successful_requests += 1
                        
                        # 更新平均响应时间
                        if response_time is not None:
                            if proxy.avg_response_time == 0:
                                proxy.avg_response_time = response_time
                            else:
                                # 指数移动平均
                                proxy.avg_response_time = 0.7 * proxy.avg_response_time + 0.3 * response_time
                    else:
                        proxy.failed_requests += 1
                    
                    # 更新成功率
                    proxy.success_rate = (proxy.successful_requests / proxy.total_requests) * 100
                    
                    # 如果成功率过低，标记为不活跃
                    if proxy.success_rate < 30 and proxy.total_requests > 10:
                        proxy.status = ProxyStatus.ERROR
                        logger.warning(f"代理 {proxy.name} (ID: {proxy.id}) 成功率过低 ({proxy.success_rate:.2f}%)，已标记为不活跃")
                    
                    db.commit()
                    
                    # 更新缓存
                    self._proxies[proxy_id] = proxy
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"更新代理状态出错: {e}")
    
    async def check_proxy_health(self, proxy_id: int = None):
        """
        检查代理健康状态
        
        Args:
            proxy_id: 特定代理ID，如果为None则检查所有代理
        """
        try:
            # 使用同步数据库访问
            db = SessionLocal()
            try:
                if proxy_id:
                    proxies = db.query(ProxyConfig).filter(ProxyConfig.id == proxy_id).all()
                else:
                    proxies = db.query(ProxyConfig).all()
                
                for proxy in proxies:
                    start_time = time.time()
                    proxy_url = proxy.get_proxy_url()
                    
                    try:
                        # 使用代理访问健康检查URL
                        async with aiohttp.ClientSession() as session:
                            async with session.get(
                                proxy.health_check_url or "https://www.baidu.com",
                                proxy=proxy_url,
                                timeout=10
                            ) as response:
                                elapsed = time.time() - start_time
                                
                                if response.status == 200:
                                    logger.info(f"代理 {proxy.name} (ID: {proxy.id}) 健康检查通过，响应时间: {elapsed:.2f}秒")
                                    proxy.status = ProxyStatus.ACTIVE
                                    proxy.avg_response_time = elapsed
                                    proxy.last_check_time = datetime.now()
                                    proxy.last_error = None
                                else:
                                    logger.warning(f"代理 {proxy.name} (ID: {proxy.id}) 健康检查失败，状态码: {response.status}")
                                    proxy.status = ProxyStatus.ERROR
                                    proxy.last_error = f"健康检查返回非200状态码: {response.status}"
                                    proxy.last_check_time = datetime.now()
                    except Exception as e:
                        logger.error(f"代理 {proxy.name} (ID: {proxy.id}) 健康检查异常: {e}")
                        proxy.status = ProxyStatus.ERROR
                        proxy.last_error = str(e)
                        proxy.last_check_time = datetime.now()
                
                db.commit()
            finally:
                db.close()
                
            # 更新代理缓存
            await self.refresh_proxies()
        except Exception as e:
            logger.error(f"代理健康检查出错: {e}")
    
    async def add_proxy(self, proxy_config: Dict[str, Any]) -> Optional[int]:
        """
        添加新代理
        
        Args:
            proxy_config: 代理配置
            
        Returns:
            Optional[int]: 新代理的ID，添加失败返回None
        """
        try:
            # 使用同步数据库访问
            db = SessionLocal()
            try:
                proxy = ProxyConfig(
                    name=proxy_config.get("name", "新代理"),
                    description=proxy_config.get("description"),
                    protocol=proxy_config.get("protocol", "socks5").upper(),
                    host=proxy_config.get("host"),
                    port=int(proxy_config.get("port")),
                    username=proxy_config.get("username"),
                    password=proxy_config.get("password"),
                    region=proxy_config.get("region"),
                    status=proxy_config.get("status", "active").upper(),
                    priority=int(proxy_config.get("priority", 0)),
                    group=proxy_config.get("group", "default"),
                    health_check_url=proxy_config.get("health_check_url", "https://www.baidu.com")
                )
                
                db.add(proxy)
                db.commit()
                db.refresh(proxy)
                
                # 更新缓存
                await self.refresh_proxies()
                
                logger.info(f"成功添加代理: {proxy.name} (ID: {proxy.id})")
                return proxy.id
            finally:
                db.close()
        except Exception as e:
            logger.error(f"添加代理出错: {e}")
            return None
    
    async def remove_proxy(self, proxy_id: int) -> bool:
        """
        删除代理
        
        Args:
            proxy_id: 代理ID
            
        Returns:
            bool: 是否删除成功
        """
        try:
            # 使用同步数据库访问
            db = SessionLocal()
            try:
                proxy = db.query(ProxyConfig).filter(ProxyConfig.id == proxy_id).first()
                if not proxy:
                    logger.warning(f"要删除的代理不存在: {proxy_id}")
                    return False
                
                db.delete(proxy)
                db.commit()
                
                # 更新缓存
                if proxy_id in self._proxies:
                    del self._proxies[proxy_id]
                for group in self._active_proxies:
                    self._active_proxies[group] = [p for p in self._active_proxies[group] if p.id != proxy_id]
                
                logger.info(f"成功删除代理: {proxy.name} (ID: {proxy.id})")
                return True
            finally:
                db.close()
        except Exception as e:
            logger.error(f"删除代理出错: {e}")
            return False


# 创建全局单例
proxy_manager = ProxyManager()


@contextlib.asynccontextmanager
async def get_db_session():
    """获取数据库会话的异步上下文管理器"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 初始化指定源的代理设置
async def init_proxy_settings(source_ids=None):
    """
    初始化需要代理的数据源配置
    
    Args:
        source_ids: 指定需要代理的数据源ID列表，如果为None则使用默认列表
    """
    if source_ids is None:
        proxy_required_sources = [
            "github", "bloomberg-markets", "bloomberg-tech", "bloomberg", 
            "hackernews", "bbc_world", "v2ex", "producthunt"
        ]
    else:
        proxy_required_sources = source_ids
    
    try:
        # 使用同步数据库访问
        db = SessionLocal()
        try:
            from app.models.source import Source
            
            for source_id in proxy_required_sources:
                source = db.query(Source).filter(Source.id == source_id).first()
                if source:
                    source.need_proxy = True
                    source.proxy_fallback = True  # 代理失败时尝试直连
                    db.commit()
                    logger.info(f"已为数据源 {source_id} 启用代理配置")
                else:
                    logger.warning(f"数据源不存在: {source_id}")
            
            # 添加默认代理配置
            # 检查是否已存在相同配置的代理
            existing_proxy = db.query(ProxyConfig).filter(
                ProxyConfig.protocol == "SOCKS5",
                ProxyConfig.host == "127.0.0.1",
                ProxyConfig.port == 10606
            ).first()
            
            if not existing_proxy:
                proxy = ProxyConfig(
                    name="Xray SOCKS5代理",
                    description="本地Xray SOCKS5代理",
                    protocol="SOCKS5",
                    host="127.0.0.1",
                    port=10606,
                    status="ACTIVE",
                    priority=1,
                    group="default"
                )
                db.add(proxy)
                db.commit()
                logger.info(f"添加了默认代理配置: {proxy.name} (ID: {proxy.id})")
            else:
                logger.info(f"默认代理配置已存在: {existing_proxy.name} (ID: {existing_proxy.id})")
        finally:
            db.close()
        
        # 刷新代理管理器
        await proxy_manager.refresh_proxies()
        
        logger.info("代理配置初始化完成")
        return True
    except Exception as e:
        logger.error(f"初始化代理配置出错: {e}")
        return False 