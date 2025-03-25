#!/usr/bin/env python
"""
运行Celery任务并监控其执行
"""
import os
import sys
import time
import argparse

# 添加当前目录和父目录到系统路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.join(current_dir, 'backend'))

# 设置环境变量
os.environ.setdefault('PYTHONPATH', current_dir)

# 导入需要的模块
from worker.celery_app import celery_app
from worker.tasks.news import schedule_source_updates
from celery.result import AsyncResult

def print_header(title):
    """打印格式化标题"""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80))
    print("=" * 80)

def monitor_task(result, timeout=60, interval=2):
    """监控任务执行"""
    task_id = result.id
    print(f"任务ID: {task_id}")
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        # 获取最新状态
        result = AsyncResult(task_id, app=celery_app)
        status = result.state
        print(f"任务状态: {status}")
        
        if status == 'SUCCESS':
            print(f"任务成功完成！")
            print(f"结果: {result.result}")
            return True
        elif status in ['FAILURE', 'REVOKED']:
            print(f"任务失败: {result.result}")
            return False
            
        print(f"等待中... (已等待 {int(time.time() - start_time)} 秒)")
        time.sleep(interval)
    
    print(f"监控超时 ({timeout} 秒)")
    return False

def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="运行并监控Celery任务")
    parser.add_argument("--use-api", action="store_true", help="使用API获取数据而不是直接从源获取")
    parser.add_argument("--api-base-url", default="http://localhost:8000", help="API基础URL")
    parser.add_argument("--timeout", type=int, default=30, help="任务监控超时时间（秒）")
    parser.add_argument("--source", default="weibo", help="要抓取的新闻源ID")
    parser.add_argument("--task", choices=["schedule", "fetch"], default="schedule",
                      help="要执行的任务: schedule (更新调度器) 或 fetch (抓取指定源)")
    args = parser.parse_args()
    
    # 设置环境变量，使任务可以获取到这些参数
    if args.use_api:
        os.environ["USE_API_FOR_DATA"] = "1"
        os.environ["API_BASE_URL"] = args.api_base_url
        print(f"将通过API获取数据: {args.api_base_url}")
    
    print_header("运行并监控Celery任务")
    
    if args.task == "schedule":
        print(f"提交任务: news.schedule_source_updates (队列: news-queue)")
        # 使用apply_async并指定queue参数
        result = schedule_source_updates.apply_async(queue='news-queue')
    else:
        print(f"提交任务: news.fetch_source_news 源: {args.source} (队列: news-queue)")
        # 导入fetch_source_news任务
        from worker.tasks.news import fetch_source_news
        # 使用apply_async并指定queue参数和source_id
        result = fetch_source_news.apply_async(args=[args.source], queue='news-queue')
    
    print(f"开始监控任务...")
    success = monitor_task(result, timeout=args.timeout)
    
    if success:
        print("✅ 任务执行成功")
    else:
        print("❌ 任务执行失败或超时")

if __name__ == "__main__":
    main() 