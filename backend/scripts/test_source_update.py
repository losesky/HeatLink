#!/usr/bin/env python
"""
测试脚本：使用ORM更新源状态
"""
import sys
from pathlib import Path
import time

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 确保加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.orm import Session
from app.db.session import SessionLocal, Base, engine
from app.models.source_stats import SourceStats
from app.models.source import Source, SourceStatus
import datetime

def test_source_update():
    """测试使用ORM更新源状态"""
    db = SessionLocal()
    try:
        # 选择一个源
        source_id = "bilibili"
        print(f"尝试更新源 {source_id} 的状态...")
        
        # 方法1: 使用get方法
        print("\n方法1: 使用get方法")
        try:
            # 为保证source_stats表存在，先创建一下
            from sqlalchemy import inspect
            inspector = inspect(engine)
            if not inspector.has_table('source_stats'):
                Base.metadata.create_all(bind=engine)
                print("创建source_stats表")
            
            # 查询源
            source = db.query(Source).filter(Source.id == source_id).first()
            if not source:
                print(f"找不到源 {source_id}")
            else:
                print(f"当前状态: {source.status}")
                
                # 备份当前状态
                original_status = source.status
                
                # 更新状态
                source.status = SourceStatus.ACTIVE
                db.commit()
                db.refresh(source)
                print(f"更新后状态: {source.status}")
                
                # 恢复原状态
                source.status = original_status
                db.commit()
                print("恢复原状态成功")
        except Exception as e:
            db.rollback()
            print(f"方法1失败: {str(e)}")
        
        # 方法2: 使用update方法
        print("\n方法2: 使用update方法")
        try:
            # 先查询当前状态
            source = db.query(Source).filter(Source.id == source_id).first()
            original_status = source.status if source else None
            print(f"当前状态: {original_status}")
            
            # 使用update语句
            result = db.query(Source).filter(Source.id == source_id).update(
                {"status": SourceStatus.ACTIVE}
            )
            db.commit()
            print(f"更新结果: {result} 行受影响")
            
            # 验证结果
            source = db.query(Source).filter(Source.id == source_id).first()
            print(f"更新后状态: {source.status if source else None}")
            
            # 恢复原状态
            if original_status:
                db.query(Source).filter(Source.id == source_id).update(
                    {"status": original_status}
                )
                db.commit()
                print("恢复原状态成功")
        except Exception as e:
            db.rollback()
            print(f"方法2失败: {str(e)}")
        
        # 方法3: 使用update_source_status函数
        print("\n方法3: 使用update_source_status函数")
        try:
            from app.crud.source_stats import update_source_status
            
            # 先查询当前状态
            source = db.query(Source).filter(Source.id == source_id).first()
            original_status = source.status if source else None
            print(f"当前状态: {original_status}")
            
            # 使用update_source_status函数
            result = update_source_status(
                db=db,
                source_id=source_id,
                success_rate=1.0,
                avg_response_time=100.0,
                total_requests=1,
                error_count=0
            )
            
            # 验证结果
            print(f"更新后状态: {result.status}")
            
            # 恢复原状态
            if original_status:
                source = db.query(Source).filter(Source.id == source_id).first()
                source.status = original_status
                db.commit()
                print("恢复原状态成功")
        except Exception as e:
            db.rollback()
            print(f"方法3失败: {str(e)}")
        
        print("\n测试完成!")
        
    except Exception as e:
        print(f"测试过程中出错: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    test_source_update() 