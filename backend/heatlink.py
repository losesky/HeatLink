#!/usr/bin/env python
"""
HeatLink CLI 工具入口脚本
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.cli.main import cli

if __name__ == "__main__":
    cli() 