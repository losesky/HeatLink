from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
import logging

from app.core.config import settings
from app.db.base_class import Base

# 设置数据库日志
db_logger = logging.getLogger("sqlalchemy.engine")

# 配置连接池参数
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=5,  # 降低连接池大小，避免过多连接
    max_overflow=10,  # 减少允许的最大连接数
    pool_timeout=60,  # 增加等待连接的超时时间
    pool_recycle=600,  # 减少连接回收时间（10分钟）以避免长时间空闲连接
    pool_pre_ping=True,  # 使用前ping连接以确保有效
    poolclass=QueuePool,  # 使用队列池
    echo=False,  # 不回显SQL语句
    echo_pool=False,  # 不回显连接池活动
    connect_args={
        "connect_timeout": 10,  # 连接超时
        "keepalives": 1,  # 启用保活
        "keepalives_idle": 30,  # 30秒没活动发送保活包
        "keepalives_interval": 10,  # 10秒重试间隔
        "keepalives_count": 5,  # 5次重试
    }
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 