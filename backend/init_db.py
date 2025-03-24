"""
初始化数据库表结构，无需依赖Alembic迁移
可直接运行解决数据库表不存在的问题
"""

import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine
import time
import json

# 加载环境变量
load_dotenv()

# 从models导入所有模型以确保它们被注册
from app.db.session import Base

# 先导入没有外键引用的模型
from app.models.category import Category
from app.models.tag import Tag

# 导入有关系的模型（顺序很重要）
from app.models.user import User, Subscription, user_favorite, user_read_history
from app.models.source_stats import SourceStats, ApiCallType
from app.models.source import Source, SourceAlias, SourceType, SourceStatus
from app.models.news import News, news_tag

# 获取数据库连接
from app.core.config import settings

def init_db():
    """
    初始化数据库表结构
    """
    print(f"连接到数据库: {settings.DATABASE_URL}")
    
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        # 创建所有表
        print("开始创建数据库表...")
        Base.metadata.create_all(engine)
        print("成功创建所有表!")
        
        return True
    except Exception as e:
        print(f"创建表时出错: {str(e)}")
        return False

def check_tables(engine):
    """检查必要的表是否已创建"""
    from sqlalchemy import inspect
    inspector = inspect(engine)
    
    required_tables = [
        'users', 'sources', 'news', 'categories', 
        'tags', 'source_stats', 'source_aliases'
    ]
    
    existing_tables = inspector.get_table_names()
    missing_tables = [table for table in required_tables if table not in existing_tables]
    
    if missing_tables:
        print(f"缺少以下表: {', '.join(missing_tables)}")
        return False
    else:
        print("所有必要的表已存在")
        return True

if __name__ == "__main__":
    if init_db():
        print("数据库初始化成功，现在您可以启动服务器了!")
    else:
        print("数据库初始化失败，请检查连接和权限设置")
        sys.exit(1) 