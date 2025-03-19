#!/usr/bin/env python
"""
源统计信息自动更新器安装脚本

此脚本用于将源统计信息自动更新器集成到现有系统中。
它会检查必要的文件，复制源代码，并提供验证步骤。
"""
import os
import sys
import shutil
import logging
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 获取项目根目录
project_root = Path(__file__).parent.parent

# 源文件路径
stats_wrapper_path = project_root / "worker" / "stats_wrapper.py"
manager_path = project_root / "worker" / "sources" / "manager.py"
main_path = project_root / "main.py"

def check_files():
    """检查必要文件是否存在"""
    files_to_check = [
        stats_wrapper_path,
        manager_path,
        main_path
    ]
    
    missing_files = []
    for file_path in files_to_check:
        if not file_path.exists():
            missing_files.append(file_path)
    
    if missing_files:
        logger.error("以下文件不存在:")
        for file_path in missing_files:
            logger.error(f"  - {file_path}")
        return False
    
    return True

def backup_files():
    """备份将要修改的文件"""
    files_to_backup = [
        manager_path,
        main_path
    ]
    
    for file_path in files_to_backup:
        backup_path = file_path.with_suffix(file_path.suffix + '.bak')
        try:
            shutil.copy2(file_path, backup_path)
            logger.info(f"已备份 {file_path} 到 {backup_path}")
        except Exception as e:
            logger.error(f"备份 {file_path} 失败: {str(e)}")
            return False
    
    return True

def verify_installation():
    """验证安装是否成功"""
    # 检查stats_wrapper.py是否包含必要的类和方法
    try:
        with open(stats_wrapper_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if "class StatsUpdater" not in content or "wrap_fetch" not in content:
                logger.error("stats_wrapper.py 文件内容不完整")
                return False
        
        # 检查manager.py是否包含对stats_wrapper的引用
        with open(manager_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if "from worker.stats_wrapper import stats_updater" not in content:
                logger.error("manager.py 未正确引用 stats_updater")
                return False
        
        # 检查main.py是否包含对stats_wrapper的初始化
        with open(main_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if "from worker.stats_wrapper import stats_updater" not in content:
                logger.error("main.py 未正确引用 stats_updater")
                return False
        
        logger.info("验证成功：所有文件都已正确修改")
        return True
    except Exception as e:
        logger.error(f"验证安装时出错: {str(e)}")
        return False

def print_instructions():
    """打印使用说明"""
    logger.info("\n使用说明:")
    logger.info("1. 源统计信息自动更新器已安装完成")
    logger.info("2. 它会在调用源适配器的fetch方法时自动更新统计信息")
    logger.info("3. 默认每小时更新一次统计记录，避免频繁的数据库操作")
    logger.info("4. 您可以在main.py的startup_event中修改更新间隔")
    logger.info("5. 重启应用后生效")

def main():
    """主函数"""
    logger.info("开始安装源统计信息自动更新器...")
    
    # 检查文件
    if not check_files():
        logger.error("安装失败：缺少必要文件")
        return 1
    
    # 备份文件
    if not backup_files():
        logger.error("安装失败：无法备份文件")
        return 1
    
    # 验证安装
    if not verify_installation():
        logger.error("安装有问题，请检查文件修改是否正确")
        logger.info("您可以从备份文件恢复")
        return 1
    
    # 打印使用说明
    print_instructions()
    
    logger.info("安装完成！")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 