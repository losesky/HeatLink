#!/bin/bash
# 安装crontab定时任务脚本
# 此脚本用于设置自动运行源健康检查的crontab任务

# 设置颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}正在设置财联社源健康检查定时任务...${NC}"

# 获取当前脚本所在目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo -e "脚本目录: ${YELLOW}$SCRIPT_DIR${NC}"

# 检查run_sources_health_check.sh是否存在
if [ ! -f "$SCRIPT_DIR/run_sources_health_check.sh" ]; then
    echo -e "${RED}错误: 未找到健康检查脚本 $SCRIPT_DIR/run_sources_health_check.sh${NC}"
    exit 1
fi

# 确保脚本有执行权限
chmod +x "$SCRIPT_DIR/run_sources_health_check.sh"
echo -e "已授予执行权限给健康检查脚本"

# 创建临时crontab文件
TEMP_CRONTAB=$(mktemp)

# 导出现有crontab配置
crontab -l > "$TEMP_CRONTAB" 2>/dev/null || echo "# 新建crontab配置文件" > "$TEMP_CRONTAB"

# 检查是否已经有相同的定时任务
if grep -q "run_sources_health_check.sh" "$TEMP_CRONTAB"; then
    echo -e "${YELLOW}警告: 检测到已存在健康检查任务，将替换原任务${NC}"
    # 移除旧的任务
    grep -v "run_sources_health_check.sh" "$TEMP_CRONTAB" > "${TEMP_CRONTAB}.new"
    mv "${TEMP_CRONTAB}.new" "$TEMP_CRONTAB"
fi

# 添加注释
echo "# 财联社源健康检查 - 每4小时执行一次" >> "$TEMP_CRONTAB"

# 添加定时任务 - 每4小时执行一次
echo "0 */4 * * * $SCRIPT_DIR/run_sources_health_check.sh" >> "$TEMP_CRONTAB"

# 安装新的crontab
crontab "$TEMP_CRONTAB"
RESULT=$?

# 清理临时文件
rm "$TEMP_CRONTAB"

if [ $RESULT -eq 0 ]; then
    echo -e "${GREEN}成功安装crontab定时任务!${NC}"
    echo -e "定时任务将每4小时执行一次源健康检查"
    echo -e "可以使用 ${YELLOW}crontab -l${NC} 命令查看已安装的定时任务"
else
    echo -e "${RED}安装crontab定时任务失败，错误码: $RESULT${NC}"
    exit 1
fi

# 设置ADMIN_EMAIL环境变量（如果需要邮件通知）
read -p "是否需要设置邮件通知? (y/n): " NEED_EMAIL
if [[ "$NEED_EMAIL" =~ ^[Yy]$ ]]; then
    read -p "请输入管理员邮箱地址: " EMAIL_ADDRESS
    
    # 检查邮箱格式是否有效
    if [[ ! "$EMAIL_ADDRESS" =~ ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
        echo -e "${RED}邮箱格式无效，不设置邮件通知${NC}"
    else
        # 修改run_sources_health_check.sh以添加ADMIN_EMAIL
        sed -i "s/^# 设置基本参数/# 设置基本参数\nADMIN_EMAIL=\"$EMAIL_ADDRESS\"/" "$SCRIPT_DIR/run_sources_health_check.sh"
        echo -e "${GREEN}已设置管理员邮箱为: $EMAIL_ADDRESS${NC}"
    fi
fi

echo -e "${GREEN}安装完成!${NC}"
exit 0 