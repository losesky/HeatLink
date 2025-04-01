#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
修复工具：检查并修复 .env 文件中的格式问题
可以处理：
1. CORS_ORIGINS 格式问题
2. 环境变量值中的命令和路径问题
3. 常见的引号和语法错误
"""

import os
import sys
import re
import json
from pathlib import Path

# 设置路径
backend_dir = Path(__file__).resolve().parent.parent
env_file = backend_dir / ".env"

def fix_env_file():
    """检查并修复 .env 文件中的格式问题"""
    if not env_file.exists():
        print(f"错误: .env 文件不存在于 {env_file}")
        return False
    
    print(f"开始检查 .env 文件: {env_file}")
    
    # 读取 .env 文件内容
    with open(env_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    fixed_lines = []
    fixed = False
    
    for i, line in enumerate(lines):
        line_num = i + 1
        original_line = line.strip()
        
        # 跳过空行和注释
        if not original_line or original_line.startswith('#'):
            fixed_lines.append(line)
            continue
        
        # 修复格式问题
        modified_line = line
        
        # 1. 修复 CORS_ORIGINS 行
        if original_line.startswith('CORS_ORIGINS='):
            try:
                # 尝试解析为 JSON
                cors_part = original_line.split('=', 1)[1]
                json.loads(cors_part)
                # 如果没有异常，说明格式正确
            except (json.JSONDecodeError, IndexError):
                # 格式不正确，进行修复
                cors_origins = re.findall(r'https?://[^,\s"]+', original_line)
                if cors_origins:
                    # 生成正确的 JSON 格式
                    fixed_cors = json.dumps(cors_origins)
                    modified_line = f"CORS_ORIGINS={fixed_cors}\n"
                    print(f"已修复 CORS_ORIGINS (行 {line_num}): {original_line} -> {modified_line.strip()}")
                    fixed = True
                else:
                    # 如果没有找到有效的 URL，使用默认值
                    default_cors = '["http://localhost:8000"]'
                    modified_line = f"CORS_ORIGINS={default_cors}\n"
                    print(f"未找到有效的 URL (行 {line_num})，使用默认值: {modified_line.strip()}")
                    fixed = True
        
        # 2. 检查常见的环境变量问题（行 13 和 25 的问题）
        if '=' in original_line:
            var_name, var_value = original_line.split('=', 1)
            var_name = var_name.strip()
            var_value = var_value.strip()
            
            # 检查值是否有引号
            if var_value and not (var_value.startswith('"') and var_value.endswith('"')) and \
               not (var_value.startswith("'") and var_value.endswith("'")):
                
                # 修复包含空格、逗号等特殊字符的值
                if ',' in var_value or ' ' in var_value:
                    # 可能是一个需要引号的值
                    quoted_value = f'"{var_value}"'
                    modified_line = f"{var_name}={quoted_value}\n"
                    print(f"已修复缺少引号 (行 {line_num}): {original_line} -> {modified_line.strip()}")
                    fixed = True
                
                # 修复 "Dev" 问题 (行 13)
                if var_value == "Dev" or var_value == "Prod":
                    quoted_value = f'"{var_value}"'
                    modified_line = f"{var_name}={quoted_value}\n"
                    print(f"已为环境名称添加引号 (行 {line_num}): {original_line} -> {modified_line.strip()}")
                    fixed = True
        
        fixed_lines.append(modified_line)
    
    if fixed:
        # 创建备份
        backup_file = env_file.with_suffix('.env.bak')
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f"已创建备份文件: {backup_file}")
        
        # 写入修复后的内容
        with open(env_file, 'w', encoding='utf-8') as f:
            f.writelines(fixed_lines)
        print(f"已更新 .env 文件")
        return True
    else:
        print("未发现需要修复的问题")
        return True

if __name__ == "__main__":
    print("-" * 50)
    print("环境配置文件(.env)修复工具")
    print("-" * 50)
    
    success = fix_env_file()
    
    if success:
        print("\n✅ 检查/修复成功！")
        sys.exit(0)
    else:
        print("\n❌ 修复失败！")
        print("请手动检查您的 .env 文件")
        sys.exit(1) 