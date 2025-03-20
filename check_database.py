#!/usr/bin/env python
"""
检查数据库中的源状态和统计信息
用于验证Celery任务是否执行成功
"""
import os
import sys
from datetime import datetime, timedelta

# 添加当前目录和父目录到系统路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.join(current_dir, 'backend'))

# 设置环境变量
os.environ.setdefault('PYTHONPATH', current_dir)

# 导入数据库相关模块
from app.db.session import SessionLocal
from app.models.source import Source
from app.models.source_stats import SourceStats
from sqlalchemy import desc, func

def print_header(title):
    """打印格式化标题"""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80))
    print("=" * 80)

def check_sources():
    """检查所有源的状态"""
    print_header("新闻源状态")
    
    db = SessionLocal()
    try:
        # 获取所有源
        sources = db.query(Source).all()
        
        print(f"共有 {len(sources)} 个新闻源")
        
        # 按最后更新时间排序
        sources.sort(key=lambda x: x.last_updated if x.last_updated else datetime(1970, 1, 1), reverse=True)
        
        # 显示最近更新的10个源
        print("\n最近更新的源:")
        for i, source in enumerate(sources[:10], 1):
            last_updated = source.last_updated.strftime('%Y-%m-%d %H:%M:%S') if source.last_updated else "从未更新"
            
            # 检查Source对象的属性
            try:
                news_count = source.news_count
            except AttributeError:
                news_count = 0
                
            print(f"{i}. {source.name} ({source.id}):")
            print(f"   状态: {source.status}")
            print(f"   最后更新: {last_updated}")
            
            # 输出所有可用的属性
            print("   属性:")
            for attr_name in dir(source):
                if not attr_name.startswith('_') and attr_name not in ['metadata', 'registry']:
                    try:
                        attr_value = getattr(source, attr_name)
                        if not callable(attr_value):
                            print(f"     {attr_name}: {attr_value}")
                    except Exception:
                        pass
                        
            if hasattr(source, 'last_error') and source.last_error:
                print(f"   最后错误: {source.last_error}")
            print()
            
        # 显示状态统计
        status_counts = {}
        for source in sources:
            status = source.status or "unknown"
            status_counts[status] = status_counts.get(status, 0) + 1
            
        print("源状态统计:")
        for status, count in status_counts.items():
            print(f"   {status}: {count}")
            
        # 检查最近一小时内更新的源数量
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recently_updated = [s for s in sources if s.last_updated and s.last_updated > one_hour_ago]
        
        print(f"\n最近一小时内更新的源数量: {len(recently_updated)}")
        
    finally:
        db.close()

def check_stats():
    """检查源统计信息"""
    print_header("源统计信息")
    
    db = SessionLocal()
    try:
        # 获取最新的源统计信息
        stats = db.query(SourceStats).order_by(desc(SourceStats.created_at)).limit(10).all()
        
        if not stats:
            print("没有源统计信息")
            return
            
        print(f"最新的源统计信息:")
        for i, stat in enumerate(stats, 1):
            created_at = stat.created_at.strftime('%Y-%m-%d %H:%M:%S') if stat.created_at else "未知"
            print(f"{i}. 源: {stat.source_id}")
            print(f"   创建时间: {created_at}")
            print(f"   成功率: {stat.success_rate:.2f}")
            print(f"   平均响应时间: {stat.avg_response_time:.2f}ms")
            print(f"   请求总数: {stat.total_requests}")
            print(f"   错误数: {stat.error_count}")
            print(f"   新闻数: {stat.news_count}")
            print()
            
        # 获取各源的统计数量
        count_by_source = db.query(
            SourceStats.source_id, 
            func.count(SourceStats.id).label('count')
        ).group_by(SourceStats.source_id).all()
        
        print(f"各源的统计记录数:")
        for source_id, count in count_by_source:
            print(f"   {source_id}: {count}")
        
    finally:
        db.close()

def main():
    """主函数"""
    print_header("数据库检查")
    
    check_sources()
    check_stats()

if __name__ == "__main__":
    main() 