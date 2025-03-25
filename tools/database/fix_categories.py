import sys
import os

# 添加项目根目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../.."))
sys.path.insert(0, project_root)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 从环境变量或配置文件获取数据库 URL
from app.core.config import settings

# 创建数据库连接
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

db = SessionLocal()
try:
    # 直接使用 SQL 更新语句，避免加载所有模型
    sql = text("UPDATE categories SET \"order\" = 0 WHERE \"order\" IS NULL")
    result = db.execute(sql)
    rows_affected = result.rowcount
    print(f'已更新 {rows_affected} 个 order 为 NULL 的分类记录')
    
    db.commit()
    print('所有记录已更新')
except Exception as e:
    print(f'更新失败: {str(e)}')
    db.rollback()
finally:
    db.close() 