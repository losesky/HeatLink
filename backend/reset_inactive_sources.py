#!/usr/bin/env python3
"""
重置所有非活跃状态(非ACTIVE)的数据源

此脚本会找出所有状态(status)不是ACTIVE的数据源，
并将它们重置为活跃状态，清除错误计数和错误信息。
"""

import sys
import os
from datetime import datetime
import logging

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from sqlalchemy import text
from app.db.session import SessionLocal

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("reset_inactive_sources")

def reset_inactive_sources():
    """重置所有非ACTIVE状态的数据源"""
    logger.info("开始重置非活跃状态的数据源")
    
    # 创建数据库会话
    db = SessionLocal()
    
    try:
        # 查询所有非ACTIVE状态的源
        inactive_sources = db.execute(
            text("SELECT id, name, status, last_error, error_count FROM sources WHERE status != 'ACTIVE'")
        ).fetchall()
        
        if not inactive_sources:
            logger.info("没有找到非活跃状态的数据源，无需重置")
            return True
        
        logger.info(f"找到 {len(inactive_sources)} 个非活跃状态的数据源")
        
        # 显示重置前的状态
        logger.info("\n重置前的数据源状态:")
        for source in inactive_sources:
            source_id, name, status, last_error, error_count = source
            logger.info(f"ID: {source_id}")
            logger.info(f"名称: {name}")
            logger.info(f"状态: {status}")
            logger.info(f"错误计数: {error_count}")
            logger.info(f"最后错误: {last_error or '无'}")
            logger.info("-" * 50)
        
        # 重置所有非活跃状态的源
        update_result = db.execute(
            text("UPDATE sources SET error_count = 0, last_error = NULL, last_update = :now, status = 'ACTIVE' WHERE status != 'ACTIVE'"),
            {"now": datetime.utcnow()}
        )
        
        affected_rows = update_result.rowcount
        logger.info(f"已重置 {affected_rows} 个数据源为活跃状态")
        
        # 提交更改
        db.commit()
        
        # 验证更新
        reset_sources = db.execute(
            text("SELECT id, name, status, last_error, last_update FROM sources WHERE id IN (SELECT id FROM sources WHERE id IN :ids)")
            .bindparams(ids=tuple([source[0] for source in inactive_sources]))
        ).fetchall()
        
        logger.info("\n重置后的数据源信息:")
        for source in reset_sources:
            source_id, name, status, last_error, last_update = source
            logger.info(f"ID: {source_id}")
            logger.info(f"名称: {name}")
            logger.info(f"状态: {status}")
            logger.info(f"最后错误: {last_error or '无'}")
            logger.info(f"最后更新时间: {last_update}")
            logger.info("-" * 50)
        
        return True
    except Exception as e:
        logger.error(f"重置非活跃数据源时出错: {e}", exc_info=True)
        db.rollback()
        return False
    finally:
        db.close()

def main():
    """主函数"""
    success = reset_inactive_sources()
    
    if success:
        logger.info("成功重置所有非活跃状态的数据源")
    else:
        logger.error("重置非活跃状态的数据源失败")
        sys.exit(1)

if __name__ == "__main__":
    main() 