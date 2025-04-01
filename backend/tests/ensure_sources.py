#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
工具脚本：确保数据库中存在必要的数据源记录
在运行测试前执行此脚本，避免外键约束错误
"""

import sys
import os
import logging
from pathlib import Path

# 添加项目根目录到Python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

# 导入必要的模块
from app.db.session import SessionLocal
from app.crud.source import get_source, create_source
from app.models.source import SourceType, SourceStatus
from app.schemas.source import SourceCreate

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ensure_sources")

# 定义需要确保存在的数据源
REQUIRED_SOURCES = [
    {
        "id": "yicai",
        "name": "第一财经",
        "description": "第一财经新闻源",
        "url": "https://www.yicai.com/",
        "type": SourceType.WEB,
        "status": "active",
        "country": "CN",
        "language": "zh-CN",
        "update_interval": 1800,  # 30分钟
        "cache_ttl": 900,  # 15分钟
        "config": {
            "use_selenium": True,
            "headless": True
        }
    },
    # 可以添加其他需要确保存在的数据源
]

def ensure_sources():
    """确保所有必要的数据源记录存在于数据库中"""
    db = SessionLocal()
    
    try:
        logger.info("开始检查和创建必要的数据源记录...")
        
        for source_info in REQUIRED_SOURCES:
            source_id = source_info["id"]
            
            # 检查源是否已存在
            db_source = get_source(db, source_id)
            
            if not db_source:
                logger.info(f"数据源 '{source_id}' 不存在，正在创建...")
                
                try:
                    # 创建源记录
                    source_data = SourceCreate(
                        id=source_id,
                        name=source_info["name"],
                        description=source_info["description"],
                        url=source_info["url"],
                        type=source_info["type"],
                        status=source_info["status"],
                        country=source_info["country"],
                        language=source_info["language"],
                        update_interval=source_info["update_interval"],
                        cache_ttl=source_info["cache_ttl"],
                        config=source_info["config"]
                    )
                    
                    db_source = create_source(db, source_data)
                    logger.info(f"成功创建数据源: {db_source.id} - {db_source.name}")
                    
                except Exception as e:
                    logger.error(f"创建数据源 '{source_id}' 失败: {str(e)}")
                    db.rollback()
            else:
                logger.info(f"数据源 '{source_id}' 已存在: {db_source.name}")
        
        logger.info("所有必要的数据源记录检查/创建完成！")
        
    except Exception as e:
        logger.error(f"确保数据源记录时出错: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    ensure_sources() 