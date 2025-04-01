#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
修复脚本：解决数据库中缺少yicai源记录导致的外键约束错误
直接运行此脚本以确保'yicai'数据源存在于数据库中
"""

import sys
import os
import logging
from pathlib import Path
import traceback

# 添加项目根目录到Python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("fix_sources")

def fix_yicai_source():
    """
    修复第一财经新闻源记录
    解决'insert or update on table "news" violates foreign key constraint "news_source_id_fkey"'错误
    """
    try:
        # 导入依赖
        from app.db.session import SessionLocal
        from app.crud.source import get_source, create_source
        from app.models.source import SourceType, SourceStatus
        from app.schemas.source import SourceCreate
        from sqlalchemy.exc import OperationalError
        
        logger.info("开始修复第一财经(yicai)数据源记录...")
        
        # 创建数据库会话
        try:
            db = SessionLocal()
            # 测试连接
            db.execute("SELECT 1")
            logger.info("数据库连接成功！")
        except OperationalError as e:
            logger.error(f"数据库连接失败: {str(e)}")
            logger.error("请检查数据库连接配置")
            return False
        
        try:
            # 检查yicai源是否存在
            db_source = get_source(db, "yicai")
            
            if db_source:
                logger.info(f"yicai数据源已存在: {db_source.name}")
                logger.info("无需修复！")
                return True
            
            # 创建yicai源
            logger.info("yicai数据源不存在，正在创建...")
            
            source_data = SourceCreate(
                id="yicai",
                name="第一财经",
                description="第一财经新闻源 - 自动修复创建",
                url="https://www.yicai.com/",
                type=SourceType.WEB,
                status="ACTIVE",
                country="CN",
                language="zh-CN",
                update_interval=1800,  # 30分钟
                cache_ttl=900,  # 15分钟
                config={
                    "use_selenium": True,
                    "headless": True
                }
            )
            
            db_source = create_source(db, source_data)
            logger.info(f"成功创建yicai数据源: {db_source.id} - {db_source.name}")
            
            return True
        
        except Exception as e:
            logger.error(f"创建yicai数据源时出错: {str(e)}")
            logger.error(traceback.format_exc())
            db.rollback()
            return False
        
        finally:
            db.close()
    
    except ImportError as e:
        logger.error(f"导入模块失败: {str(e)}")
        logger.error("请确保依赖库已安装并且项目路径配置正确")
        return False
    
    except Exception as e:
        logger.error(f"发生未预期的错误: {str(e)}")
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    print("-" * 50)
    print("第一财经(yicai)数据源修复工具")
    print("用于解决外键约束错误: news_source_id_fkey")
    print("-" * 50)
    
    success = fix_yicai_source()
    
    if success:
        print("\n✅ 修复成功！")
        print("现在您可以运行测试脚本而不会遇到外键约束错误")
        sys.exit(0)
    else:
        print("\n❌ 修复失败！")
        print("请查看上面的错误信息，并手动解决问题")
        sys.exit(1) 