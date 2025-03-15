#!/usr/bin/env python3
import sys
import argparse
from celery.result import AsyncResult

# 添加当前目录到 sys.path
sys.path.insert(0, ".")

from worker.celery_app import celery_app


def get_task_status(task_id):
    """
    获取任务状态和结果
    """
    result = AsyncResult(task_id, app=celery_app)
    
    print(f"Task ID: {task_id}")
    print(f"Task State: {result.state}")
    
    if result.state == 'SUCCESS':
        print(f"Task Result: {result.result}")
    elif result.state == 'FAILURE':
        print(f"Task Error: {result.result}")
    elif result.state == 'PENDING':
        print("Task is still pending or not found")
    elif result.state == 'STARTED':
        print("Task is currently running")
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Check Celery task status')
    parser.add_argument('task_id', help='Task ID to check')
    parser.add_argument('--wait', action='store_true', help='Wait for task to complete')
    parser.add_argument('--timeout', type=int, default=10, help='Timeout in seconds when waiting')
    
    args = parser.parse_args()
    
    result = get_task_status(args.task_id)
    
    if args.wait and result.state not in ('SUCCESS', 'FAILURE'):
        print(f"Waiting for task to complete (timeout: {args.timeout}s)...")
        try:
            task_result = result.get(timeout=args.timeout)
            print(f"Task completed with result: {task_result}")
        except Exception as e:
            print(f"Error waiting for task: {str(e)}")


if __name__ == "__main__":
    main() 