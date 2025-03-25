#!/bin/bash

# 设置颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 显示标题
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}   HeatLink 系统清理脚本   ${NC}"
echo -e "${GREEN}=======================================${NC}"

# 清理Python缓存文件
echo -e "${YELLOW}清理Python缓存文件...${NC}"
find . -name "__pycache__" -type d -exec rm -rf {} +
find . -name "*.pyc" -delete

# 清理临时文件
echo -e "${YELLOW}清理临时文件...${NC}"
rm -f celery.pid
rm -f backend/celerybeat-schedule
rm -f backend/*.html
rm -f backend/*.json

# 清理日志文件（可选）
read -p "是否清理日志文件? (y/n): " clean_logs
if [ "$clean_logs" = "y" ]; then
    echo -e "${YELLOW}清理日志文件...${NC}"
    find logs -name "*.log" -type f -mtime +7 -delete
    echo -e "${GREEN}已删除7天前的日志文件${NC}"
fi

# 创建备份目录（如果不存在）
BACKUP_DIR="db_backups"
if [ ! -d "$BACKUP_DIR" ]; then
    mkdir -p "$BACKUP_DIR"
    echo -e "${YELLOW}创建数据备份目录: $BACKUP_DIR${NC}"
fi

# 整理测试文件（可选）
read -p "是否整理测试文件到tests目录? (y/n): " organize_tests
if [ "$organize_tests" = "y" ]; then
    echo -e "${YELLOW}整理测试文件...${NC}"
    mkdir -p tests
    find . -maxdepth 1 -name "test_*.py" -exec mv {} tests/ \;
    find . -maxdepth 1 -name "*_test.py" -exec mv {} tests/ \;
    echo -e "${GREEN}已将测试文件移动到tests目录${NC}"
fi

# 检查过期备份文件（超过30天的备份）
echo -e "${YELLOW}检查过期备份文件...${NC}"
if [ -d "$BACKUP_DIR" ]; then
    old_backups=$(find "$BACKUP_DIR" -name "*.sql" -type f -mtime +30)
    if [ -n "$old_backups" ]; then
        echo -e "${YELLOW}以下备份文件已超过30天:${NC}"
        echo "$old_backups"
        read -p "是否删除这些过期备份? (y/n): " clean_backups
        if [ "$clean_backups" = "y" ]; then
            find "$BACKUP_DIR" -name "*.sql" -type f -mtime +30 -delete
            echo -e "${GREEN}已删除过期备份文件${NC}"
        fi
    else
        echo -e "${GREEN}没有找到过期备份文件${NC}"
    fi
fi

# 整理环境文件（可选）
read -p "是否清理重复的环境文件? (y/n): " clean_env
if [ "$clean_env" = "y" ]; then
    echo -e "${YELLOW}整理环境文件...${NC}"
    # 备份当前环境文件
    cp .env ".env.backup_$(date +%Y%m%d_%H%M%S)" 2>/dev/null
    echo -e "${GREEN}已备份当前环境配置${NC}"
fi

echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}系统清理完成!${NC}"
echo -e "${GREEN}=======================================${NC}" 