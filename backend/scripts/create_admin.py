#!/usr/bin/env python
"""
初始化脚本：创建管理员用户
"""
import sys
import os
from pathlib import Path
import getpass
import secrets
import string

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 确保加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

# 修复bcrypt版本检测问题
try:
    import bcrypt
    # 如果bcrypt没有__about__属性，添加一个模拟的__about__模块
    if not hasattr(bcrypt, '__about__'):
        class DummyAbout:
            __version__ = bcrypt.__version__ if hasattr(bcrypt, '__version__') else '4.3.0'
        bcrypt.__about__ = DummyAbout()
        print(f"已修复bcrypt版本检测，使用版本: {bcrypt.__about__.__version__}")
except Exception as e:
    print(f"无法修复bcrypt版本检测: {str(e)}")

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash

def create_admin():
    """交互式创建管理员用户"""
    db = SessionLocal()
    
    try:
        # 输入管理员电子邮件
        email = input("请输入管理员电子邮件: ")
        
        # 检查是否已存在此邮箱用户
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            print(f"用户 {email} 已存在")
            assign_admin = input("是否将该用户设为管理员? (y/n): ").lower()
            if assign_admin == 'y':
                # 检查是否已经是管理员
                if existing_user.is_superuser:
                    print(f"用户 {email} 已经是管理员")
                else:
                    # 设置为管理员
                    existing_user.is_superuser = True
                    db.commit()
                    print(f"用户 {email} 已设为管理员")
            return
        
        # 输入用户名
        username = input("请输入用户名: ")
        
        # 输入并确认密码
        while True:
            password = getpass.getpass("请输入密码: ")
            confirm_password = getpass.getpass("请再次输入密码确认: ")
            
            if password != confirm_password:
                print("两次输入的密码不匹配，请重新输入")
                continue
            
            if len(password) < 8:
                print("密码长度必须至少为8个字符，请重新输入")
                continue
            
            break
        
        # 创建用户
        hashed_password = get_password_hash(password)
        user = User(
            email=email,
            username=username,
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        print(f"管理员用户 {email} 创建成功")
    
    except Exception as e:
        db.rollback()
        print(f"创建管理员用户时出错: {str(e)}")
    finally:
        db.close()

def create_admin_auto(email="admin@example.com", password=None, full_name="Admin User"):
    """非交互式创建管理员用户，用于自动化脚本"""
    if not password:
        # 生成随机密码
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for i in range(12))
    
    db = SessionLocal()
    
    try:
        # 生成用户名 (从邮箱中提取)
        username = email.split('@')[0]
        
        # 检查是否已存在此邮箱用户
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            print(f"用户 {email} 已存在")
            
            # 检查是否已经是管理员
            if existing_user.is_superuser:
                print(f"用户 {email} 已经是管理员")
            else:
                # 设置为管理员
                existing_user.is_superuser = True
                db.commit()
                print(f"用户 {email} 已设为管理员")
            
            return existing_user
        
        # 创建用户
        hashed_password = get_password_hash(password)
        user = User(
            email=email,
            username=username,
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        print(f"管理员用户 {email} 创建成功，密码: {password}")
        return user
    
    except Exception as e:
        db.rollback()
        print(f"创建管理员用户时出错: {str(e)}")
        return None
    finally:
        db.close()

if __name__ == "__main__":
    # 如果作为独立脚本运行，使用交互模式
    import argparse
    
    parser = argparse.ArgumentParser(description="创建管理员用户")
    parser.add_argument("--non-interactive", action="store_true", help="非交互模式")
    parser.add_argument("--email", default="admin@example.com", help="管理员邮箱")
    parser.add_argument("--password", help="管理员密码 (不指定则生成随机密码)")
    parser.add_argument("--username", help="管理员用户名 (不指定则从邮箱生成)")
    
    args = parser.parse_args()
    
    if args.non_interactive:
        create_admin_auto(email=args.email, password=args.password)
    else:
        create_admin() 