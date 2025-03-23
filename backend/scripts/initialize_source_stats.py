#!/usr/bin/env python
"""
初始化源统计信息脚本

此脚本用于初始化所有活跃但缺少统计信息的数据源的统计记录。
"""

import sys
import os
import logging
from sqlalchemy.orm import Session

# 将项目根目录添加到 Python 路径，以便正确导入其他模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.db.session import SessionLocal
from app.models.source import Source
from app.models.source_stats import SourceStats, ApiCallType
from app.crud.source_stats import create_source_stats

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger("initialize_source_stats")

def initialize_missing_stats(db: Session):
    """为所有缺少统计信息的活跃源初始化统计数据"""
    # 查询所有没有统计记录的活跃源
    missing_stats_sources = db.query(Source).filter(
        Source.status == 'ACTIVE',
        ~Source.id.in_(db.query(SourceStats.source_id).distinct())
    ).all()
    
    logger.info(f"找到 {len(missing_stats_sources)} 个缺少统计信息的活跃源")
    
    for source in missing_stats_sources:
        # 为每个缺失统计信息的源创建初始记录，默认为内部调用类型
        create_source_stats(
            db=db,
            source_id=source.id,
            success_rate=1.0,  # 初始成功率设为100%
            avg_response_time=0.0,
            total_requests=0,
            error_count=0,
            news_count=0,
            api_type=ApiCallType.INTERNAL  # 默认为内部调用
        )
        logger.info(f"为源 {source.id} ({source.name}) 创建了初始统计记录 (内部类型)")
        
        # 同时创建一个外部类型的记录
        create_source_stats(
            db=db,
            source_id=source.id,
            success_rate=1.0,  # 初始成功率设为100%
            avg_response_time=0.0,
            total_requests=0,
            error_count=0,
            news_count=0,
            api_type=ApiCallType.EXTERNAL  # 外部调用
        )
        logger.info(f"为源 {source.id} ({source.name}) 创建了初始统计记录 (外部类型)")
    
    db.commit()
    return len(missing_stats_sources)

def main():
    """主函数"""
    db = SessionLocal()
    try:
        count = initialize_missing_stats(db)
        logger.info(f"成功初始化了 {count} 个源的统计信息")
    finally:
        db.close()

if __name__ == "__main__":
    main() 