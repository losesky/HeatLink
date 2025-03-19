#!/usr/bin/env python
"""
为thepaper-selenium源添加统计记录

此脚本用于为thepaper-selenium源创建初始统计记录。
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 确保加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.crud.source_stats import create_source_stats
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def add_stats_for_thepaper():
    """为thepaper-selenium源添加初始统计记录"""
    source_id = "thepaper-selenium"
    db = SessionLocal()
    try:
        # 创建初始统计记录
        stats = create_source_stats(
            db=db,
            source_id=source_id,
            success_rate=1.0,  # 初始成功率为100%
            avg_response_time=500.0,  # 假设平均响应时间为500毫秒
            total_requests=1,  # 初始请求次数为1
            error_count=0      # 无错误
        )
        logger.info(f"已为新闻源 {source_id} 创建初始统计记录，ID: {stats.id}")
        return True
    except Exception as e:
        logger.error(f"为新闻源 {source_id} 创建统计记录时出错: {str(e)}")
        return False
    finally:
        db.close()

if __name__ == "__main__":
    logger.info("开始为thepaper-selenium源创建统计记录...")
    
    success = add_stats_for_thepaper()
    
    if success:
        logger.info("已成功为thepaper-selenium源创建统计记录")
    else:
        logger.error("为thepaper-selenium源创建统计记录失败")
        sys.exit(1) 