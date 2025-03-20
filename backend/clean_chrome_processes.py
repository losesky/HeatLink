#!/usr/bin/env python
"""
Chrome进程清理脚本

该脚本用于检测和清理系统中残留的Chrome和ChromeDriver进程。
可以在crontab中设置定期运行，或在需要时手动执行。

用法示例:
    python clean_chrome_processes.py [--force] [--quiet]

参数:
    --force  强制清理所有Chrome相关进程，而不仅是可能泄露的进程
    --quiet  静默模式，仅输出错误信息
"""

import os
import sys
import argparse
import logging
import time
import datetime
from typing import List, Dict, Any, Optional

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("chrome_cleaner")

def setup_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='清理残留的Chrome相关进程')
    parser.add_argument('--force', action='store_true', help='强制清理所有Chrome相关进程')
    parser.add_argument('--quiet', action='store_true', help='静默模式，减少输出')
    return parser.parse_args()

def find_and_kill_chrome_processes(force: bool = False) -> int:
    """查找并杀死Chrome相关进程"""
    import psutil
    
    try:
        chrome_processes = []
        chromedriver_processes = []
        zombie_processes = []
        
        for process in psutil.process_iter(['pid', 'name', 'cmdline', 'status', 'create_time']):
            try:
                # 检查进程名是否包含chrome或chromium
                if process.info['name'] and ('chrome' in process.info['name'].lower() or 'chromium' in process.info['name'].lower()):
                    process_age = time.time() - process.info.get('create_time', 0)
                    
                    # 1. 检查是否为由Python脚本启动的Chrome (通过检查命令行参数)
                    if process.info['cmdline'] and any('--remote-debugging-port' in arg for arg in process.info['cmdline']):
                        chrome_processes.append(process)
                    # 2. 检查是否为僵尸进程
                    elif process.info['status'] == 'zombie':
                        zombie_processes.append(process)
                    # 3. 检查是否为无头模式Chrome
                    elif process.info['cmdline'] and any('--headless' in arg for arg in process.info['cmdline']):
                        chrome_processes.append(process)
                    # 4. 检查进程运行时间是否超过阈值
                    elif process_age > 3600:  # 超过1小时
                        chrome_processes.append(process)
                    # 5. 如果是强制模式，添加所有Chrome进程
                    elif force:
                        chrome_processes.append(process)
                        
                # 检查是否为ChromeDriver进程
                elif process.info['name'] and 'chromedriver' in process.info['name'].lower():
                    process_age = time.time() - process.info.get('create_time', 0)
                    
                    # 判断是否长时间运行
                    if process_age > 3600 or force:  # 超过1小时或强制模式
                        chromedriver_processes.append(process)
                # 检查是否为ChromeDriver (通过命令行参数)
                elif process.info['cmdline'] and any('chromedriver' in arg.lower() for arg in process.info['cmdline']):
                    process_age = time.time() - process.info.get('create_time', 0)
                    
                    # 判断是否长时间运行
                    if process_age > 3600 or force:  # 超过1小时或强制模式
                        chromedriver_processes.append(process)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        # 如果没有要清理的进程，提前返回
        total_processes = len(chrome_processes) + len(chromedriver_processes) + len(zombie_processes)
        if total_processes == 0:
            logger.info("没有发现需要清理的Chrome相关进程")
            return 0
            
        logger.info(f"发现 {len(chrome_processes)} 个Chrome进程, {len(chromedriver_processes)} 个ChromeDriver进程, "
                   f"{len(zombie_processes)} 个僵尸进程需要清理")
        
        # 按顺序处理：先是Chrome进程，然后是ChromeDriver进程，最后是僵尸进程
        killed_count = 0
        
        # 杀死找到的Chrome进程
        for process in chrome_processes:
            try:
                process.terminate()
                logger.info(f"已终止Chrome进程 (PID: {process.pid})")
                killed_count += 1
            except Exception as e:
                logger.error(f"终止Chrome进程 (PID: {process.pid}) 失败: {str(e)}")
                try:
                    # 如果无法正常终止，尝试强制结束
                    process.kill()
                    logger.info(f"已强制结束Chrome进程 (PID: {process.pid})")
                    killed_count += 1
                except Exception as e:
                    logger.error(f"强制结束Chrome进程 (PID: {process.pid}) 失败: {str(e)}")
        
        # 杀死找到的ChromeDriver进程
        for process in chromedriver_processes:
            try:
                # 获取子进程
                children = process.children(recursive=True)
                # 先终止子进程
                for child in children:
                    try:
                        child.terminate()
                        logger.info(f"已终止ChromeDriver子进程 (PID: {child.pid})")
                        killed_count += 1
                    except Exception:
                        try:
                            child.kill()
                            logger.info(f"已强制结束ChromeDriver子进程 (PID: {child.pid})")
                            killed_count += 1
                        except Exception as e:
                            logger.error(f"强制结束ChromeDriver子进程 (PID: {child.pid}) 失败: {str(e)}")
                
                # 然后终止ChromeDriver进程
                process.terminate()
                logger.info(f"已终止ChromeDriver进程 (PID: {process.pid})")
                killed_count += 1
            except Exception as e:
                logger.error(f"终止ChromeDriver进程 (PID: {process.pid}) 失败: {str(e)}")
                try:
                    # 如果无法正常终止，尝试强制结束
                    process.kill()
                    logger.info(f"已强制结束ChromeDriver进程 (PID: {process.pid})")
                    killed_count += 1
                except Exception as e:
                    logger.error(f"强制结束ChromeDriver进程 (PID: {process.pid}) 失败: {str(e)}")
        
        # 处理僵尸进程
        for process in zombie_processes:
            try:
                # 尝试查找并终止僵尸进程的父进程
                try:
                    parent = psutil.Process(process.ppid())
                    parent.terminate()
                    logger.info(f"已终止僵尸进程的父进程 (PID: {parent.pid})")
                    killed_count += 1
                except Exception:
                    pass
                
                # 尝试kill僵尸进程本身
                process.kill()
                logger.info(f"已尝试强制结束僵尸进程 (PID: {process.pid})")
                killed_count += 1
            except Exception as e:
                logger.error(f"处理僵尸进程 (PID: {process.pid}) 失败: {str(e)}")
                    
        # 等待进程实际终止
        all_processes = chrome_processes + chromedriver_processes + zombie_processes
        gone, still_alive = psutil.wait_procs(all_processes, timeout=3)
        for process in still_alive:
            try:
                process.kill()
                logger.info(f"强制结束未响应的进程 (PID: {process.pid})")
                killed_count += 1
            except Exception as e:
                logger.error(f"无法强制结束进程 (PID: {process.pid}): {str(e)}")
                
        return killed_count
    except ImportError:
        logger.error("未安装psutil模块，无法查找和杀死Chrome进程")
        return 0
    except Exception as e:
        logger.error(f"查找和杀死Chrome进程时出错: {str(e)}")
        return 0

def main():
    """主函数"""
    args = setup_args()
    
    if args.quiet:
        logger.setLevel(logging.ERROR)
    
    # 输出开始信息
    start_time = datetime.datetime.now()
    if not args.quiet:
        logger.info(f"Chrome进程清理开始，时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        if args.force:
            logger.info("强制模式：将清理所有Chrome相关进程")
    
    # 执行清理
    killed_count = find_and_kill_chrome_processes(force=args.force)
    
    # 输出结束信息
    end_time = datetime.datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    if not args.quiet:
        logger.info(f"Chrome进程清理完成，时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"共清理 {killed_count} 个进程，耗时 {elapsed:.2f} 秒")
    
    return killed_count

if __name__ == "__main__":
    main() 