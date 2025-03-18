#!/usr/bin/env python
"""
调试脚本：验证SourceStatus枚举与数据库的映射关系
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 确保加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import SessionLocal

def debug_source_status():
    """测试SourceStatus枚举与数据库的映射关系"""
    db = SessionLocal()
    try:
        # 从这里单独导入，避免循环导入问题
        from app.models.source import SourceStatus, Source
        
        # 1. 打印SourceStatus枚举的定义
        print("\n===== SourceStatus枚举定义 =====")
        print(f"枚举成员: {SourceStatus.__members__}")
        print(f"枚举值: {[s.value for s in SourceStatus]}")
        
        # 2. 测试从字符串到枚举的转换
        print("\n===== 字符串到枚举的转换 =====")
        for status_str in ['active', 'error', 'warning', 'inactive']:
            try:
                status_enum = SourceStatus(status_str)
                print(f"'{status_str}' -> {status_enum} (成功)")
            except ValueError as e:
                print(f"'{status_str}' -> 转换失败: {str(e)}")
        
        # 3. 查询数据库中的状态值
        print("\n===== 数据库中的状态值 =====")
        # 使用原生SQL查询，避免模型关系问题
        result = db.execute(text("SELECT id, status FROM sources LIMIT 5"))
        for row in result:
            print(f"Source {row[0]}: status = '{row[1]}'")
        
        # 4. 测试直接更新状态
        print("\n===== 测试直接更新状态 =====")
        # 直接使用SQL更新状态
        source_id = "bilibili"
        try:
            # 先获取原始状态
            original_status = db.execute(
                text("SELECT status FROM sources WHERE id = :id"),
                {"id": source_id}
            ).scalar()
            print(f"原始状态: {source_id} -> {original_status}")
            
            # 尝试更新状态
            db.execute(
                text("UPDATE sources SET status = :status WHERE id = :id"),
                {"id": source_id, "status": "active"}
            )
            db.commit()
            
            # 验证更新结果
            new_status = db.execute(
                text("SELECT status FROM sources WHERE id = :id"),
                {"id": source_id}
            ).scalar()
            print(f"更新后状态: {source_id} -> {new_status} (成功)")
            
            # 恢复原状态
            db.execute(
                text("UPDATE sources SET status = :status WHERE id = :id"),
                {"id": source_id, "status": original_status}
            )
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"更新失败: {str(e)}")

        print("\n测试完成!")
        
    except Exception as e:
        print(f"测试过程中出错: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    debug_source_status() 