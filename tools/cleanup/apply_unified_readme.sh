#!/bin/bash

# 设置颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 显示标题
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}   HeatLink README统一脚本   ${NC}"
echo -e "${GREEN}=======================================${NC}"

# 备份当前的README文件
echo -e "${YELLOW}备份当前的README文件...${NC}"
if [ -f "README.md" ]; then
    backup_name="README.md.backup_$(date +%Y%m%d_%H%M%S)"
    cp README.md "$backup_name"
    echo -e "${GREEN}当前README已备份为 $backup_name${NC}"
fi

# 复制统一的README文件
echo -e "${YELLOW}应用统一的README文件...${NC}"
if [ -f "UNIFIED_README.md" ]; then
    cp UNIFIED_README.md README.md
    echo -e "${GREEN}统一的README文件已应用${NC}"
else
    echo -e "${RED}错误: 找不到统一的README文件 (UNIFIED_README.md)${NC}"
    exit 1
fi

# 整理其他README文件
echo -e "${YELLOW}整理其他README文件...${NC}"

# 创建archived/readme目录
mkdir -p archived/readme

# 移动其他README文件到archived/readme目录
if [ -f "README.changes.md" ]; then
    cp README.changes.md archived/readme/
    echo -e "${GREEN}README.changes.md 已复制到 archived/readme/${NC}"
fi

# 说明
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}README文件整理完成!${NC}"
echo -e "${YELLOW}主README文件: README.md${NC}"
echo -e "${YELLOW}备份文件: $backup_name${NC}"
echo -e "${YELLOW}其他README文件已归档到: archived/readme/${NC}"
echo -e "${GREEN}=======================================${NC}" 