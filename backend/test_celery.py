#!/usr/bin/env python3
"""
测试Celery任务系统，用于手动触发任务并验证系统功能
"""

import os
import sys
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

# 设置环境变量以便导入应用模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from celery import Celery
from celery.result import AsyncResult

from app.db.session import SessionLocal
from app.crud.source_stats import get_latest_stats
from worker.celery_app import celery_app
from worker.tasks.news import fetch_source_news


def print_header(title: str) -> None:
    """打印格式化的标题"""
    print("\n" + "=" * 50)
    print(f"{title:^50}")
    print("=" * 50 + "\n")


def main():
    """主函数，运行测试流程"""
    print_header("HeatLink Celery任务系统测试")
    
    # 1. 测试连接到Celery
    print("1. 测试连接到Celery...")
    try:
        workers = celery_app.control.inspect().active()
        if not workers:
            print("❌ 无法连接到任何Celery worker，请确保Celery服务正在运行")
            return
        
        print(f"✅ 成功连接到Celery，发现 {len(workers)} 个活动worker")
        for worker_name, tasks in workers.items():
            concurrency = len(tasks) if tasks else 0
            print(f"   - {worker_name}: {concurrency} 个并发进程")
        
    except Exception as e:
        print(f"❌ 连接到Celery时出错: {e}")
        return
    
    # 2. 查看已注册的任务
    print("\n2. 查看已注册的任务...")
    try:
        registered = celery_app.control.inspect().registered()
        if not registered:
            print("❌ 无法获取已注册的任务")
        else:
            print()
            for worker_name, tasks in registered.items():
                print(f"在Worker '{worker_name}'上注册的任务:")
                news_tasks = [task for task in tasks if task.startswith('news.')]
                for task in news_tasks:
                    print(f"   ✅ {task}")
    except Exception as e:
        print(f"❌ 获取已注册任务时出错: {e}")
    
    # 3. 获取源的初始news_count
    print("\n3. 获取源的初始news_count...")
    source_id = "zhihu"  # 使用知乎作为测试源
    db = SessionLocal()
    try:
        initial_stats = get_latest_stats(db, source_id)
        if initial_stats:
            print(f"源 '{source_id}' 的初始统计信息:")
            print(f"   新闻数量: {initial_stats.news_count}")
            print(f"   最后响应时间: {initial_stats.last_response_time}")
        else:
            print(f"❌ 无法获取源 '{source_id}' 的统计信息")
            db.close()
            return
    except Exception as e:
        print(f"❌ 获取源统计信息时出错: {e}")
        db.close()
        return
    finally:
        db.close()
    
    # 4. 运行测试任务
    print(f"\n4. 运行测试任务: fetch_source_news...")
    try:
        print(f"   📤 发送任务: news.fetch_source_news({source_id})")
        task = fetch_source_news.delay(source_id)
        print(f"   🔄 任务ID: {task.id}")
        
        # 等待任务完成
        print("   ⌛ 等待任务完成...")
        timeout = 30  # 增加超时时间到30秒
        start_time = time.time()
        while not task.ready() and time.time() - start_time < timeout:
            time.sleep(1)
        
        if task.ready():
            if task.successful():
                result = task.get()
                print(f"   ✅ 任务成功完成! 结果: {result}")
            else:
                print(f"   ❌ 任务执行失败: {task.result}")
        else:
            print("   ❌ 任务执行超时，但这不一定意味着任务失败")
            print("      抓取任务可能仍在后台运行")
    except Exception as e:
        print(f"   ❌ 运行任务时出错: {e}")
    
    # 5. 检查更新后的news_count
    print("\n5. 检查更新后的news_count...")
    time.sleep(2)  # 等待数据更新
    db = SessionLocal()
    try:
        updated_stats = get_latest_stats(db, source_id)
        if updated_stats:
            print(f"源 '{source_id}' 的更新后统计信息:")
            print(f"   新闻数量: {updated_stats.news_count}")
            print(f"   最后响应时间: {updated_stats.last_response_time}")
            
            if updated_stats.news_count > initial_stats.news_count:
                print(f"   ✅ news_count 已成功更新! 增加了 {updated_stats.news_count - initial_stats.news_count} 个新闻")
            else:
                print(f"   ⚠️ news_count 没有增加，但任务可能仍在运行或没有新的内容")
            
            if updated_stats.last_response_time > initial_stats.last_response_time:
                print(f"   ✅ last_response_time 已成功更新!")
            else:
                print(f"   ⚠️ last_response_time 没有更新")
                
        else:
            print(f"❌ 无法获取源 '{source_id}' 的统计信息")
    except Exception as e:
        print(f"❌ 获取更新后的源统计信息时出错: {e}")
    finally:
        db.close()

    print("\n" + "=" * 50)
    print(f"{'测试完成':^50}")
    print("=" * 50)


if __name__ == "__main__":
    main() 