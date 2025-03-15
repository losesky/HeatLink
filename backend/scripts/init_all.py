#!/usr/bin/env python
"""
主初始化脚本：运行所有初始化脚本
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 确保加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

# 导入初始化函数
from init_sources import init_db as init_sources
from init_tags import init_tags
from create_admin import create_admin

def init_all():
    """运行所有初始化脚本"""
    print("=" * 50)
    print("开始初始化数据库...")
    print("=" * 50)
    
    # 初始化新闻源
    print("\n[1/3] 初始化新闻源...")
    init_sources()
    
    # 初始化标签
    print("\n[2/3] 初始化标签...")
    init_tags()
    
    # 询问是否创建管理员用户
    print("\n[3/3] 创建管理员用户...")
    create_admin_choice = input("是否创建管理员用户？(y/n): ").lower()
    if create_admin_choice == 'y':
        create_admin()
    
    print("\n" + "=" * 50)
    print("数据库初始化完成！")
    print("=" * 50)

if __name__ == "__main__":
    init_all() 