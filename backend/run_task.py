#!/usr/bin/env python3
import sys
import argparse

# 添加当前目录到 sys.path
sys.path.insert(0, ".")

from worker.celery_app import celery_app
from worker.tasks.news import (
    fetch_high_frequency_sources,
    fetch_medium_frequency_sources,
    fetch_low_frequency_sources,
    fetch_all_news,
    fetch_source_news,
    cleanup_old_news,
    analyze_news_trends
)


def run_task(task_name, *args, **kwargs):
    """
    运行指定的任务
    """
    tasks = {
        'high_freq': fetch_high_frequency_sources,
        'medium_freq': fetch_medium_frequency_sources,
        'low_freq': fetch_low_frequency_sources,
        'all_news': fetch_all_news,
        'source_news': fetch_source_news,
        'cleanup': cleanup_old_news,
        'analyze': analyze_news_trends
    }
    
    if task_name not in tasks:
        print(f"Unknown task: {task_name}")
        print(f"Available tasks: {', '.join(tasks.keys())}")
        return None
    
    task = tasks[task_name]
    
    # 执行任务
    result = task.delay(*args, **kwargs)
    
    print(f"Task {task_name} started with ID: {result.id}")
    print(f"Current state: {result.state}")
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Run Celery tasks')
    parser.add_argument('task', choices=[
        'high_freq', 'medium_freq', 'low_freq', 'all_news', 
        'source_news', 'cleanup', 'analyze'
    ], help='Task to run')
    parser.add_argument('--source-id', help='Source ID for source_news task')
    parser.add_argument('--days', type=int, default=30, help='Days for cleanup or analyze tasks')
    parser.add_argument('--wait', action='store_true', help='Wait for task to complete')
    parser.add_argument('--timeout', type=int, default=60, help='Timeout in seconds when waiting')
    
    args = parser.parse_args()
    
    # 准备任务参数
    task_args = []
    task_kwargs = {}
    
    if args.task == 'source_news' and args.source_id:
        task_args.append(args.source_id)
    
    if args.task in ('cleanup', 'analyze'):
        task_kwargs['days'] = args.days
    
    # 运行任务
    result = run_task(args.task, *task_args, **task_kwargs)
    
    if result and args.wait:
        print(f"Waiting for task to complete (timeout: {args.timeout}s)...")
        try:
            task_result = result.get(timeout=args.timeout)
            print(f"Task completed with result: {task_result}")
        except Exception as e:
            print(f"Error waiting for task: {str(e)}")


if __name__ == "__main__":
    main() 