#!/usr/bin/env python
"""
数据验证脚本：验证数据库中的数据一致性，可以单独运行
"""
import sys
import os
import json
import argparse
from pathlib import Path

# 添加项目根目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../.."))
sys.path.insert(0, project_root)

# 修复bcrypt版本检测问题
try:
    import bcrypt
    # 如果缺少__about__模块，添加一个dummy version
    if not hasattr(bcrypt, '__about__'):
        class DummyAbout:
            __version__ = bcrypt.__version__ if hasattr(bcrypt, '__version__') else '4.0.0'
        bcrypt.__about__ = DummyAbout()
except ImportError:
    pass

# 确保加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text, inspect, MetaData
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

def verify_data(verbose=False, fix=False):
    """验证数据库中的数据一致性"""
    try:
        # 获取数据库连接
        from app.core.config import settings
        engine = create_engine(settings.DATABASE_URL)
        inspector = inspect(engine)
        metadata = MetaData()
        metadata.reflect(bind=engine)
        
        # 创建会话
        Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = Session()
        
        # 检查必要的表是否存在
        required_tables = ['sources', 'categories', 'tags', 'users', 'news']
        missing_tables = [t for t in required_tables if t not in inspector.get_table_names()]
        
        if missing_tables:
            print(f"错误: 缺少必要的表: {missing_tables}")
            return False, {"missing_tables": missing_tables}
        
        # 初始化数据统计结构
        data_counts = {}
        
        # 检查各个表的数据数量
        for table in inspector.get_table_names():
            try:
                result = session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                data_counts[table] = count
                
                if verbose:
                    print(f"表 {table}: {count} 条记录")
            except Exception as e:
                print(f"检查表 {table} 时出错: {str(e)}")
        
        # 核心表数据验证规则
        validation_issues = []
        
        # 1. 检查sources表
        if data_counts.get('sources', 0) == 0:
            validation_issues.append("sources表为空，需要初始化数据")
        
        # 2. 检查categories表
        if data_counts.get('categories', 0) == 0:
            validation_issues.append("categories表为空，需要初始化数据")
        
        # 3. 检查tags表
        if data_counts.get('tags', 0) == 0:
            validation_issues.append("tags表为空，需要初始化数据")
            
        # 4. 检查用户表
        if data_counts.get('users', 0) == 0:
            validation_issues.append("users表为空，需要初始化管理员用户")
        
        # 5. 检查外键完整性 - sources 与 categories 的关联
        try:
            # 检查是否有分类ID不在categories表中的source
            result = session.execute(text("""
                SELECT s.id, s.category_id 
                FROM sources s 
                LEFT JOIN categories c ON s.category_id = c.id 
                WHERE s.category_id IS NOT NULL AND c.id IS NULL
            """))
            invalid_sources = result.fetchall()
            
            if invalid_sources:
                source_ids = [r[0] for r in invalid_sources]
                validation_issues.append(f"存在{len(invalid_sources)}个无效分类ID的source记录: {source_ids[:5]}...")
                
                # 修复方案 - 如果指定了修复选项
                if fix:
                    if len(invalid_sources) > 0:
                        try:
                            # 获取默认分类ID或创建一个
                            result = session.execute(text("SELECT id FROM categories LIMIT 1"))
                            default_category_id = result.scalar()
                            
                            if not default_category_id:
                                # 如果没有分类，创建一个
                                from app.models.category import Category
                                default_category = Category(name="默认分类", description="自动修复创建的默认分类")
                                session.add(default_category)
                                session.flush()
                                default_category_id = default_category.id
                            
                            # 更新无效的记录
                            for source_id, _ in invalid_sources:
                                session.execute(text(f"""
                                    UPDATE sources SET category_id = :category_id 
                                    WHERE id = :source_id
                                """).bindparams(category_id=default_category_id, source_id=source_id))
                            
                            session.commit()
                            print(f"已修复{len(invalid_sources)}个无效分类ID的source记录")
                        except Exception as e:
                            session.rollback()
                            print(f"修复source分类关联时出错: {str(e)}")
        except Exception as e:
            validation_issues.append(f"检查sources与categories关联时出错: {str(e)}")
        
        # 6. 数据完整性检查 - sources配置
        try:
            result = session.execute(text("""
                SELECT id FROM sources 
                WHERE config IS NULL OR config::text = '{}'
            """))
            invalid_configs = result.fetchall()
            
            if invalid_configs:
                source_ids = [r[0] for r in invalid_configs]
                validation_issues.append(f"存在{len(invalid_configs)}个配置为空的source记录: {source_ids[:5]}...")
                
                # 修复方案 - 如果指定了修复选项
                if fix:
                    try:
                        # 为每个空配置的源添加默认配置
                        for source_id in source_ids:
                            # 获取源类型
                            source_info = session.execute(
                                text("SELECT type FROM sources WHERE id = :id"),
                                {"id": source_id}
                            ).fetchone()
                            
                            if not source_info:
                                continue
                                
                            source_type = source_info[0]
                            
                            # 根据源类型设置默认配置
                            default_config = {}
                            if source_id == 'thepaper':
                                default_config = {
                                    "use_selenium": True,
                                    "headless": True,
                                    "wait_time": 10
                                }
                            elif source_id.startswith('coolapk'):
                                default_config = {
                                    "use_api": True,
                                    "limit": 20
                                }
                            elif source_id.startswith('cls'):
                                default_config = {
                                    "use_selenium": True,
                                    "use_direct_api": False,
                                    "use_scraping": True,
                                    "use_backup_api": True
                                }
                            else:
                                # 通用默认配置
                                default_config = {
                                    "limit": 20,
                                    "active": True
                                }
                                
                            # 更新源配置
                            config_json = json.dumps(default_config)
                            session.execute(
                                text("UPDATE sources SET config = cast(:config AS jsonb) WHERE id = :id"),
                                {"id": source_id, "config": config_json}
                            )
                            
                        session.commit()
                        print(f"已为{len(source_ids)}个源添加默认配置")
                    except Exception as e:
                        session.rollback()
                        print(f"修复源配置时出错: {str(e)}")
        except Exception as e:
            validation_issues.append(f"检查sources配置时出错: {str(e)}")
        
        # 输出验证结果
        if not validation_issues:
            print("\n✅ 数据验证通过，所有核心表数据完整")
            return True, data_counts
        else:
            print("\n❌ 数据验证失败，发现以下问题:")
            for issue in validation_issues:
                print(f" - {issue}")
            
            if fix:
                print("\n⚠️ 已尝试自动修复部分问题，请重新运行验证")
            else:
                print("\n提示: 使用 --fix 参数运行此脚本可尝试自动修复部分问题")
            
            return False, {"issues": validation_issues, "counts": data_counts}
    
    except SQLAlchemyError as e:
        print(f"数据库连接或查询出错: {str(e)}")
        return False, {"error": str(e)}
    except Exception as e:
        print(f"验证过程出现未知错误: {str(e)}")
        return False, {"error": str(e)}
    finally:
        if 'session' in locals():
            session.close()

def export_data(output_file=None):
    """导出核心数据以便迁移"""
    try:
        from app.core.config import settings
        engine = create_engine(settings.DATABASE_URL)
        
        # 创建会话
        Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = Session()
        
        export_data = {
            "categories": [],
            "sources": [],
            "tags": []
        }
        
        # 导出分类
        result = session.execute(text("SELECT id, name, description FROM categories"))
        for row in result:
            export_data["categories"].append({
                "id": row[0],
                "name": row[1],
                "description": row[2]
            })
        
        # 导出sources
        result = session.execute(text("""
            SELECT id, name, description, url, type, status, 
                   category_id, country, language, config
            FROM sources
        """))
        for row in result:
            export_data["sources"].append({
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "url": row[3],
                "type": row[4],
                "status": row[5],
                "category_id": row[6],
                "country": row[7], 
                "language": row[8],
                "config": row[9]
            })
        
        # 导出tags
        result = session.execute(text("SELECT id, name, description FROM tags"))
        for row in result:
            export_data["tags"].append({
                "id": row[0],
                "name": row[1],
                "description": row[2]
            })
        
        # 导出到文件或返回数据
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            print(f"数据已成功导出到: {output_file}")
        
        return True, export_data
    except Exception as e:
        print(f"导出数据时出错: {str(e)}")
        return False, {"error": str(e)}
    finally:
        if 'session' in locals():
            session.close()

def import_data(input_file, clear_existing=False):
    """从导出文件导入核心数据"""
    try:
        # 加载导入数据
        with open(input_file, 'r', encoding='utf-8') as f:
            import_data = json.load(f)
        
        from app.core.config import settings
        engine = create_engine(settings.DATABASE_URL)
        
        # 创建会话
        Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = Session()
        
        # 如果需要清除现有数据
        if clear_existing:
            print("清除现有数据...")
            try:
                session.execute(text("DELETE FROM sources"))
                session.execute(text("DELETE FROM tags"))
                session.execute(text("DELETE FROM categories"))
                session.commit()
            except Exception as e:
                session.rollback()
                print(f"清除数据时出错: {str(e)}")
                return False, {"error": str(e)}
        
        # 导入分类
        print(f"正在导入 {len(import_data.get('categories', []))} 个分类...")
        for category in import_data.get('categories', []):
            try:
                # 检查是否已存在
                result = session.execute(text("SELECT id FROM categories WHERE id = :id").bindparams(id=category['id']))
                if result.scalar() is None:
                    session.execute(text("""
                        INSERT INTO categories (id, name, description)
                        VALUES (:id, :name, :description)
                    """).bindparams(
                        id=category['id'],
                        name=category['name'],
                        description=category['description']
                    ))
            except Exception as e:
                print(f"导入分类 {category['id']} 时出错: {str(e)}")
        
        session.commit()
        
        # 导入sources
        print(f"正在导入 {len(import_data.get('sources', []))} 个数据源...")
        for source in import_data.get('sources', []):
            try:
                # 检查是否已存在
                result = session.execute(text("SELECT id FROM sources WHERE id = :id").bindparams(id=source['id']))
                if result.scalar() is None:
                    session.execute(text("""
                        INSERT INTO sources (id, name, description, url, type, status, 
                                           category_id, country, language, config)
                        VALUES (:id, :name, :description, :url, :type, :status,
                               :category_id, :country, :language, :config::jsonb)
                    """).bindparams(
                        id=source['id'],
                        name=source['name'],
                        description=source['description'],
                        url=source['url'],
                        type=source['type'],
                        status=source['status'],
                        category_id=source['category_id'],
                        country=source['country'],
                        language=source['language'],
                        config=json.dumps(source['config'])
                    ))
            except Exception as e:
                print(f"导入数据源 {source['id']} 时出错: {str(e)}")
        
        session.commit()
        
        # 导入tags
        print(f"正在导入 {len(import_data.get('tags', []))} 个标签...")
        for tag in import_data.get('tags', []):
            try:
                # 检查是否已存在
                result = session.execute(text("SELECT id FROM tags WHERE id = :id").bindparams(id=tag['id']))
                if result.scalar() is None:
                    session.execute(text("""
                        INSERT INTO tags (id, name, description)
                        VALUES (:id, :name, :description)
                    """).bindparams(
                        id=tag['id'],
                        name=tag['name'],
                        description=tag['description']
                    ))
            except Exception as e:
                print(f"导入标签 {tag['id']} 时出错: {str(e)}")
        
        session.commit()
        
        print("数据导入完成")
        return True, {"imported": {
            "categories": len(import_data.get('categories', [])),
            "sources": len(import_data.get('sources', [])),
            "tags": len(import_data.get('tags', []))
        }}
    except Exception as e:
        print(f"导入数据时出错: {str(e)}")
        return False, {"error": str(e)}
    finally:
        if 'session' in locals():
            session.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="数据库数据验证和导出导入工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # 验证命令
    verify_parser = subparsers.add_parser("verify", help="验证数据库数据")
    verify_parser.add_argument("--verbose", "-v", action="store_true", help="显示详细信息")
    verify_parser.add_argument("--fix", "-f", action="store_true", help="尝试自动修复问题")
    
    # 导出命令
    export_parser = subparsers.add_parser("export", help="导出核心数据")
    export_parser.add_argument("--output", "-o", required=True, help="输出文件路径")
    
    # 导入命令
    import_parser = subparsers.add_parser("import", help="导入核心数据")
    import_parser.add_argument("--input", "-i", required=True, help="输入文件路径")
    import_parser.add_argument("--clear", "-c", action="store_true", help="导入前清除现有数据")
    
    args = parser.parse_args()
    
    if args.command == "verify":
        success, _ = verify_data(verbose=args.verbose, fix=args.fix)
        sys.exit(0 if success else 1)
    elif args.command == "export":
        success, _ = export_data(output_file=args.output)
        sys.exit(0 if success else 1)
    elif args.command == "import":
        success, _ = import_data(input_file=args.input, clear_existing=args.clear)
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(1) 