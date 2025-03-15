#!/usr/bin/env python
"""
创建管理员用户脚本
"""
import sys
import os
import getpass
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 确保加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash

def create_admin():
    """创建管理员用户"""
    print("=" * 50)
    print("创建管理员用户")
    print("=" * 50)
    
    # 获取用户输入
    username = input("请输入管理员用户名: ")
    email = input("请输入管理员邮箱: ")
    password = getpass.getpass("请输入管理员密码: ")
    confirm_password = getpass.getpass("请再次输入管理员密码: ")
    
    # 验证密码
    if password != confirm_password:
        print("两次输入的密码不一致，请重新运行脚本。")
        return
    
    if len(password) < 8:
        print("密码长度不能少于8个字符，请重新运行脚本。")
        return
    
    # 创建管理员用户
    db = SessionLocal()
    try:
        # 检查用户是否已存在
        existing_user = db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        
        if existing_user:
            print(f"用户已存在: {existing_user.username} ({existing_user.email})")
            return
        
        # 创建新用户
        hashed_password = get_password_hash(password)
        admin_user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=True
        )
        
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        print(f"管理员用户创建成功: {admin_user.username} ({admin_user.email})")
    except Exception as e:
        db.rollback()
        print(f"创建管理员用户失败: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    create_admin() 