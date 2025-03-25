#!/bin/bash

# 设置颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}   HeatLink 冗余文件清理工具   ${NC}"
echo -e "${GREEN}=======================================${NC}"

# 确认操作
echo -e "${YELLOW}此操作将删除已经移动到tools目录的冗余脚本文件。${NC}"
read -p "确认要继续吗? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo -e "${YELLOW}操作已取消${NC}"
    exit 0
fi

# 删除根目录下已移动到tools的冗余文件
echo -e "${YELLOW}删除根目录下的冗余文件...${NC}"

redundant_files=(
    "./check_cls_api.py"
    "./check_cls_with_selenium.py"
    "./check_thepaper_structure.py"
    "./verify_thepaper_fix.py"
    "./fix_thepaper_source.py"
    "./fix_database.sh"
    "./health_check.sh"
    "./run_celery.sh"
    "./stop_celery.sh"
    "./run_task.py"
    "./monitor_tasks.py"
    "./cleanup_scripts.sh"
    "./apply_unified_readme.sh"
    "./MAINTENANCE_SCRIPTS_REPORT.md"
)

for file in "${redundant_files[@]}"; do
    if [ -f "$file" ]; then
        rm "$file"
        echo "已删除: $file"
    fi
done

# 确保不删除正在运行的cleanup.sh
if [ -f "./cleanup.sh" ] && [ "$(basename "$(readlink -f "$0")")" != "cleanup.sh" ]; then
    rm "./cleanup.sh"
    echo "已删除: ./cleanup.sh"
fi

echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}冗余文件清理完成!${NC}"
echo -e "${GREEN}=======================================${NC}"
echo -e "所有维护工具现在位于 ${YELLOW}./tools/${NC} 目录下。"
echo -e "${GREEN}=======================================${NC}"
