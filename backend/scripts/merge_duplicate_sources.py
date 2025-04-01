#!/usr/bin/env python
"""
合并重复新闻源脚本：将重复的新闻源合并，移动关联的新闻
"""
import sys
import os
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 确保加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import SessionLocal

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 需要合并的新闻源对照表
# 格式: {'保留的source_id': ['要合并的source_id列表']}
SOURCES_TO_MERGE = {
    'cls': ['cls-article'],              # 保留财联社，合并财联社文章
    'bloomberg': ['bloomberg-china']     # 保留彭博社，合并彭博社中国
}


def merge_sources(db: Session):
    """合并重复的新闻源"""
    try:
        for target_id, source_ids in SOURCES_TO_MERGE.items():
            logger.info(f"开始处理合并: {target_id} <-- {', '.join(source_ids)}")
            
            # 1. 检查目标新闻源是否存在
            target_source = db.execute(
                text("SELECT id, name, type, status FROM sources WHERE id = :id"),
                {"id": target_id}
            ).fetchone()
            
            if not target_source:
                logger.error(f"目标新闻源 {target_id} 不存在，跳过合并")
                continue
            
            logger.info(f"目标新闻源: ID: {target_source[0]}, 名称: {target_source[1]}, 类型: {target_source[2]}, 状态: {target_source[3]}")
            
            # 2. 处理每个要合并的新闻源
            for source_id in source_ids:
                logger.info(f"正在处理新闻源 {source_id}")
                
                # 检查新闻源是否存在
                source_info = db.execute(
                    text("SELECT id, name, type, status FROM sources WHERE id = :id"),
                    {"id": source_id}
                ).fetchone()
                
                if not source_info:
                    logger.warning(f"新闻源 {source_id} 不存在，跳过")
                    continue
                
                logger.info(f"待合并的新闻源: ID: {source_info[0]}, 名称: {source_info[1]}, 类型: {source_info[2]}, 状态: {source_info[3]}")
                
                # 3. 检查有多少新闻项需要迁移
                news_count = db.execute(
                    text("SELECT COUNT(*) FROM news WHERE source_id = :source_id"),
                    {"source_id": source_id}
                ).scalar()
                
                logger.info(f"新闻源 {source_id} 有 {news_count} 条新闻需要迁移")
                
                if news_count > 0:
                    # 4. 检查是否有冲突（相同的original_id）
                    conflicts = db.execute(
                        text("""
                        SELECT n1.id, n1.original_id FROM news n1 
                        JOIN news n2 ON n1.original_id = n2.original_id 
                        WHERE n1.source_id = :target_id AND n2.source_id = :source_id
                        """),
                        {"target_id": target_id, "source_id": source_id}
                    ).fetchall()
                    
                    if conflicts:
                        conflict_count = len(conflicts)
                        logger.warning(f"发现 {conflict_count} 条新闻项存在相同的original_id")
                        
                        # 记录冲突的ID，用于后续处理
                        conflict_originals = [c[1] for c in conflicts]
                        
                        # 删除待合并源中冲突的项目
                        db.execute(
                            text("DELETE FROM news WHERE source_id = :source_id AND original_id IN :ids"),
                            {"source_id": source_id, "ids": tuple(conflict_originals)}
                        )
                        logger.info(f"已删除 {source_id} 中 {conflict_count} 条冲突的新闻项")
                    
                    # 5. 更新剩余的新闻项到目标新闻源
                    updated_rows = db.execute(
                        text("UPDATE news SET source_id = :target_id WHERE source_id = :source_id"),
                        {"target_id": target_id, "source_id": source_id}
                    ).rowcount
                    
                    logger.info(f"已将 {updated_rows} 条新闻项从 {source_id} 迁移到 {target_id}")
                
                # 6. 先删除source_stats表中的相关记录以避免外键约束错误
                try:
                    stats_count = db.execute(
                        text("SELECT COUNT(*) FROM source_stats WHERE source_id = :source_id"),
                        {"source_id": source_id}
                    ).scalar()
                    
                    if stats_count > 0:
                        db.execute(
                            text("DELETE FROM source_stats WHERE source_id = :source_id"),
                            {"source_id": source_id}
                        )
                        logger.info(f"已删除 {source_id} 在source_stats表中的 {stats_count} 条记录")
                except Exception as e:
                    logger.warning(f"删除source_stats记录时出错: {str(e)}")
                
                # 检查是否还有其他表引用此source_id
                try:
                    # 查找所有外键引用的表
                    fk_tables = db.execute(
                        text("""
                        SELECT tc.table_name, kcu.column_name
                        FROM information_schema.table_constraints AS tc 
                        JOIN information_schema.key_column_usage AS kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                        JOIN information_schema.constraint_column_usage AS ccu
                        ON ccu.constraint_name = tc.constraint_name
                        AND ccu.table_schema = tc.table_schema
                        WHERE tc.constraint_type = 'FOREIGN KEY' 
                        AND ccu.table_name = 'sources'
                        AND ccu.column_name = 'id'
                        """)
                    ).fetchall()
                    
                    for table_name, column_name in fk_tables:
                        if table_name != 'news':  # news表已经处理过了
                            count = db.execute(
                                text(f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} = :source_id"),
                                {"source_id": source_id}
                            ).scalar()
                            
                            if count > 0:
                                logger.info(f"从 {table_name} 表中删除 {source_id} 的 {count} 条相关记录")
                                db.execute(
                                    text(f"DELETE FROM {table_name} WHERE {column_name} = :source_id"),
                                    {"source_id": source_id}
                                )
                except Exception as e:
                    logger.warning(f"清理其他表引用时出错: {str(e)}")
                
                # 7. 删除已合并的新闻源
                db.execute(
                    text("DELETE FROM sources WHERE id = :id"),
                    {"id": source_id}
                )
                logger.info(f"已删除新闻源 {source_id}")
                
                # 8. 更新目标新闻源的news_count
                db.execute(
                    text("""
                    UPDATE sources 
                    SET news_count = (SELECT COUNT(*) FROM news WHERE source_id = :id)
                    WHERE id = :id
                    """),
                    {"id": target_id}
                )
                logger.info(f"已更新 {target_id} 的news_count")
            
        # 提交所有更改
        db.commit()
        logger.info("所有新闻源合并完成，更改已提交")
        
    except Exception as e:
        db.rollback()
        logger.error(f"合并新闻源时出错: {str(e)}")
        raise
    finally:
        db.close()


def main():
    """脚本主入口"""
    logger.info("开始执行新闻源合并脚本")
    
    # 创建数据库会话
    db = SessionLocal()
    
    try:
        # 执行合并操作
        merge_sources(db)
        logger.info("新闻源合并完成")
    except Exception as e:
        logger.error(f"执行失败: {str(e)}")
    finally:
        db.close()


if __name__ == "__main__":
    main() 