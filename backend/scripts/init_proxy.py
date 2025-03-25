#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
初始化代理设置
为指定的数据源启用代理配置，并添加默认的Xray/V2Ray代理配置
"""

import os
import sys
import asyncio
import datetime
import logging

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
from app.models.source import Source
from app.models.proxy import ProxyConfig, ProxyProtocol, ProxyStatus

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/init_proxy.log")
    ]
)
logger = logging.getLogger(__name__)


async def init_proxy():
    """初始化代理配置"""
    logger.info("开始初始化代理配置...")
    
    # 需要代理的数据源
    proxy_required_sources = [
        "github", "bloomberg-markets", "bloomberg-tech", "bloomberg", 
        "hackernews", "bbc_world", "bloomberg-china", "v2ex", "producthunt"
    ]
    
    try:
        # 在数据库中设置这些源需要使用代理
        db = SessionLocal()
        try:
            for source_id in proxy_required_sources:
                source = db.query(Source).filter(Source.id == source_id).first()
                if source:
                    source.need_proxy = True
                    source.proxy_fallback = True  # 代理失败时尝试直连
                    logger.info(f"已为数据源 {source_id} 启用代理配置")
                else:
                    logger.warning(f"数据源不存在: {source_id}")
            
            # 提交变更
            db.commit()
            
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
            
            logger.info("代理配置初始化成功")
        finally:
            db.close()
    
        # 显示当前配置情况
        db = SessionLocal()
        try:
            # 检查数据源配置
            sources = db.query(Source).filter(Source.need_proxy == True).all()
            logger.info(f"已配置需要代理的数据源: {len(sources)}个")
            for source in sources:
                logger.info(f"  - {source.id} ({source.name})")
            
            # 检查代理配置
            proxies = db.query(ProxyConfig).all()
            logger.info(f"当前配置的代理: {len(proxies)}个")
            for proxy in proxies:
                logger.info(f"  - ID: {proxy.id}, 名称: {proxy.name}, 地址: {proxy.protocol.lower()}://{proxy.host}:{proxy.port}, 状态: {proxy.status}")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"初始化代理配置出错: {e}")
    
    logger.info("代理配置初始化完成")


def main():
    """主函数"""
    try:
        # 运行异步初始化函数
        asyncio.run(init_proxy())
    except KeyboardInterrupt:
        logger.info("操作被用户中断")
    except Exception as e:
        logger.error(f"初始化代理配置出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 