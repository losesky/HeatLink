#!/usr/bin/env python
"""
Celery任务监控脚本
此脚本用于监控Celery任务的执行状态和结果
"""
import os
import sys
import time
from datetime import datetime, timedelta
import argparse

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../.."))
sys.path.insert(0, project_root)

# 设置环境变量
os.environ.setdefault('PYTHONPATH', project_root)

# 导入需要的模块
from worker.celery_app import celery_app
from celery.result import AsyncResult

def print_header(title):
    """打印格式化标题"""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80))
    print("=" * 80)

def print_task_status(task_id, task_name=None):
    """打印任务状态信息"""
    try:
        result = AsyncResult(task_id, app=celery_app)
        status = result.state
        
        status_emoji = {
            'PENDING': '⏳',
            'STARTED': '🔄',
            'SUCCESS': '✅',
            'FAILURE': '❌',
            'RETRY': '🔁',
            'REVOKED': '🚫',
        }.get(status, '❓')
        
        task_info = f"{task_id}"
        if task_name:
            task_info = f"{task_name} ({task_id})"
            
        print(f"{status_emoji} 任务: {task_info}")
        print(f"   状态: {status}")
        
        if status == 'SUCCESS':
            print(f"   结果: {result.result}")
        elif status == 'FAILURE':
            print(f"   错误: {result.result}")
            
        return status
        
    except Exception as e:
        print(f"❌ 获取任务状态失败: {str(e)}")
        return None

def get_recent_tasks(since=None, limit=10, task_prefix=None):
    """获取最近的任务"""
    try:
        i = celery_app.control.inspect()
        
        # 获取已完成的任务
        completed = []
        revoked = []
        active = []
        scheduled = []
        reserved = []
        
        # 获取正在执行的任务
        active_tasks = i.active() or {}
        for worker_name, tasks in active_tasks.items():
            for task in tasks:
                if task_prefix and not task['name'].startswith(task_prefix):
                    continue
                task['worker'] = worker_name
                task['status'] = 'ACTIVE'
                active.append(task)
        
        # 获取预留的任务
        reserved_tasks = i.reserved() or {}
        for worker_name, tasks in reserved_tasks.items():
            for task in tasks:
                if task_prefix and not task['name'].startswith(task_prefix):
                    continue
                task['worker'] = worker_name
                task['status'] = 'RESERVED'
                reserved.append(task)
        
        # 获取计划中的任务
        scheduled_tasks = i.scheduled() or {}
        for worker_name, tasks in scheduled_tasks.items():
            for task in tasks:
                if task_prefix and not task['request']['name'].startswith(task_prefix):
                    continue
                task_info = task['request']
                task_info['worker'] = worker_name
                task_info['status'] = 'SCHEDULED'
                task_info['eta'] = task['eta']
                scheduled.append(task_info)
        
        # 按时间排序并限制数量
        all_tasks = active + reserved + scheduled
        all_tasks.sort(key=lambda x: x.get('time_start', 0) if isinstance(x.get('time_start'), (int, float)) else 0, reverse=True)
        
        return all_tasks[:limit]
    
    except Exception as e:
        print(f"❌ 获取任务列表失败: {str(e)}")
        return []

def monitor_task(task_id, timeout=60, interval=2):
    """监控指定任务直到完成或超时"""
    print_header(f"监控任务 {task_id}")
    
    start_time = time.time()
    result = AsyncResult(task_id, app=celery_app)
    
    while time.time() - start_time < timeout:
        status = print_task_status(task_id)
        
        if status in ['SUCCESS', 'FAILURE', 'REVOKED']:
            return status
            
        print(f"等待中... (已等待 {int(time.time() - start_time)} 秒)")
        time.sleep(interval)
    
    print(f"❗ 监控超时 ({timeout} 秒)")
    return None

def list_recent_tasks(limit=10, task_prefix=None):
    """列出最近的任务"""
    print_header(f"最近的任务 (限制 {limit} 个)")
    
    tasks = get_recent_tasks(limit=limit, task_prefix=task_prefix)
    
    if not tasks:
        print("没有找到任务")
        return
    
    for i, task in enumerate(tasks, 1):
        status = task.get('status', 'UNKNOWN')
        status_emoji = {
            'ACTIVE': '🔄',
            'RESERVED': '⏳',
            'SCHEDULED': '🕒',
            'UNKNOWN': '❓'
        }.get(status, '❓')
        
        task_id = task.get('id')
        task_name = task.get('name', 'Unknown')
        
        print(f"{i}. {status_emoji} [{status}] {task_name}")
        print(f"   ID: {task_id}")
        
        if status == 'ACTIVE':
            worker = task.get('worker', 'Unknown')
            runtime = task.get('time_start', 0)
            if isinstance(runtime, (int, float)) and runtime > 0:
                runtime_str = datetime.fromtimestamp(runtime).strftime('%Y-%m-%d %H:%M:%S')
                print(f"   Worker: {worker}, 开始时间: {runtime_str}")
            else:
                print(f"   Worker: {worker}")
                
        elif status == 'SCHEDULED':
            eta = task.get('eta')
            if eta:
                print(f"   计划执行时间: {eta}")
                
        print("")

def get_task_count():
    """获取任务数量统计"""
    try:
        i = celery_app.control.inspect()
        
        stats = {}
        
        # 活动任务
        active = i.active() or {}
        stats['active'] = sum(len(tasks) for tasks in active.values())
        
        # 预留任务
        reserved = i.reserved() or {}
        stats['reserved'] = sum(len(tasks) for tasks in reserved.values())
        
        # 计划任务
        scheduled = i.scheduled() or {}
        stats['scheduled'] = sum(len(tasks) for tasks in scheduled.values())
        
        return stats
    
    except Exception as e:
        print(f"❌ 获取任务统计失败: {str(e)}")
        return {'active': 0, 'reserved': 0, 'scheduled': 0}

def show_worker_stats():
    """显示Worker统计信息"""
    print_header("Worker统计信息")
    
    try:
        i = celery_app.control.inspect()
        stats = i.stats() or {}
        
        if not stats:
            print("未找到活动的Worker")
            return
        
        for worker_name, worker_stats in stats.items():
            print(f"Worker: {worker_name}")
            
            # 进程池信息
            pool = worker_stats.get('pool', {})
            max_concurrency = pool.get('max-concurrency', 'Unknown')
            print(f"   并发: {max_concurrency}")
            
            # 系统信息
            hostname = worker_stats.get('hostname', 'Unknown')
            pid = worker_stats.get('pid', 'Unknown')
            print(f"   主机: {hostname}, PID: {pid}")
            
            # 处理器统计
            broker = worker_stats.get('broker', {})
            transport = broker.get('transport', 'Unknown')
            print(f"   Broker: {transport}")
            
            # 任务统计
            processed = worker_stats.get('total', {}).get('news.schedule_source_updates', {}).get('total', 0)
            if processed > 0:
                print(f"   已处理'schedule_source_updates'任务: {processed}")
                
            print("")
    
    except Exception as e:
        print(f"❌ 获取Worker统计失败: {str(e)}")

def dashboard():
    """显示任务仪表盘"""
    print_header("Celery任务仪表盘")
    
    try:
        # 显示Worker状态
        i = celery_app.control.inspect()
        stats = i.stats() or {}
        
        print(f"活动Worker: {len(stats)}")
        for worker_name in stats.keys():
            print(f"   - {worker_name}")
            
        # 显示任务统计
        task_stats = get_task_count()
        
        print(f"\n任务统计:")
        print(f"   活动任务: {task_stats['active']}")
        print(f"   预留任务: {task_stats['reserved']}")
        print(f"   计划任务: {task_stats['scheduled']}")
        print(f"   总任务数: {sum(task_stats.values())}")
        
        # 显示最近的任务
        print("\n最近的任务:")
        recent_tasks = get_recent_tasks(limit=5)
        
        if not recent_tasks:
            print("   没有任务记录")
        else:
            for i, task in enumerate(recent_tasks, 1):
                status = task.get('status', 'UNKNOWN')
                task_name = task.get('name', 'Unknown')
                task_id = task.get('id', 'Unknown')
                print(f"   {i}. [{status}] {task_name} (ID: {task_id})")
    
    except Exception as e:
        print(f"❌ 获取仪表盘数据失败: {str(e)}")

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Celery任务监控工具")
    
    subparsers = parser.add_subparsers(dest="command", help="操作命令")
    
    # 监控任务
    monitor_parser = subparsers.add_parser("monitor", help="监控指定的任务")
    monitor_parser.add_argument("task_id", help="要监控的任务ID")
    monitor_parser.add_argument("--timeout", type=int, default=60, help="监控超时时间(秒)")
    monitor_parser.add_argument("--interval", type=int, default=2, help="状态检查间隔(秒)")
    
    # 列出最近的任务
    list_parser = subparsers.add_parser("list", help="列出最近的任务")
    list_parser.add_argument("--limit", type=int, default=10, help="要显示的任务数量")
    list_parser.add_argument("--prefix", help="任务名称前缀过滤(例如 'news.')")
    
    # Worker统计
    subparsers.add_parser("workers", help="显示Worker统计信息")
    
    # 仪表盘
    subparsers.add_parser("dashboard", help="显示任务仪表盘")
    
    return parser.parse_args()

def main():
    """主函数"""
    args = parse_args()
    
    if args.command == "monitor":
        monitor_task(args.task_id, args.timeout, args.interval)
    elif args.command == "list":
        list_recent_tasks(args.limit, args.prefix)
    elif args.command == "workers":
        show_worker_stats()
    elif args.command == "dashboard":
        dashboard()
    else:
        # 默认显示仪表盘
        dashboard()

if __name__ == "__main__":
    main() 