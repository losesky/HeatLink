#!/usr/bin/env python
"""
修复worker/stats_wrapper.py中的update_source_stats函数调用

此脚本用于修复stats_wrapper中的代码，确保它能正确地使用news_count和last_response_time参数
"""
import os
import sys
import re
import logging

# 添加当前目录和父目录到系统路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("stats_wrapper_fix")

def fix_stats_wrapper():
    """修复stats_wrapper.py文件"""
    # 定位stats_wrapper.py文件
    stats_wrapper_file = os.path.join(current_dir, 'stats_wrapper.py')
    
    if not os.path.exists(stats_wrapper_file):
        logger.error(f"未找到文件: {stats_wrapper_file}")
        return False
    
    logger.info(f"开始修复文件: {stats_wrapper_file}")
    
    # 备份原始文件
    backup_file = f"{stats_wrapper_file}.bak"
    try:
        import shutil
        shutil.copy2(stats_wrapper_file, backup_file)
        logger.info(f"已创建备份文件: {backup_file}")
    except Exception as e:
        logger.error(f"创建备份文件失败: {str(e)}")
        return False
    
    # 读取文件内容
    try:
        with open(stats_wrapper_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"读取文件失败: {str(e)}")
        return False
    
    # 查找并修复update_source_stats调用
    pattern = r'update_source_stats\(db, source_id,\s+success_rate=success_rate,\s+avg_response_time=avg_response_time,\s+last_response_time=stats\["last_response_time"\],\s+total_requests=total_requests,\s+error_count=error_count,\s+news_count=stats\["news_count"\]\)'
    
    if re.search(pattern, content, re.MULTILINE | re.DOTALL):
        logger.info("update_source_stats调用已经包含了所有必要的参数，无需修复")
        return True
    
    # 构建替换字符串
    replacement = """update_source_stats(db, source_id, 
                                         success_rate=success_rate,
                                         avg_response_time=avg_response_time,
                                         last_response_time=stats["last_response_time"],
                                         total_requests=total_requests,
                                         error_count=error_count,
                                         news_count=stats["news_count"])"""
    
    # 查找旧的调用模式
    old_pattern = r'update_source_stats\(db, source_id,\s+success_rate=success_rate,\s+avg_response_time=avg_response_time,\s+.*?\)'
    
    # 执行替换
    new_content = re.sub(old_pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)
    
    # 检查是否进行了替换
    if new_content == content:
        logger.warning("未找到需要替换的模式，可能文件已被修改或模式不匹配")
        return False
    
    # 写入修改后的内容
    try:
        with open(stats_wrapper_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        logger.info("已成功修复stats_wrapper.py文件")
        return True
    except Exception as e:
        logger.error(f"写入文件失败: {str(e)}")
        # 如果写入失败，尝试恢复备份
        try:
            shutil.copy2(backup_file, stats_wrapper_file)
            logger.info("已从备份恢复原始文件")
        except Exception as e2:
            logger.error(f"恢复备份失败: {str(e2)}")
        return False

if __name__ == "__main__":
    if fix_stats_wrapper():
        print("✅ 修复成功!")
    else:
        print("❌ 修复失败，请查看日志") 