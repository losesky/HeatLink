#!/bin/bash

# 日志颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}     停止 Celery 服务     ${NC}"
echo -e "${BLUE}=====================================${NC}"

# 获取当前目录
CURRENT_DIR=$(pwd)
echo -e "${GREEN}当前目录: ${CURRENT_DIR}${NC}"

# 停止所有Celery工作进程
echo -e "${YELLOW}正在停止所有Celery工作进程...${NC}"
pkill -f "celery worker" || echo -e "${RED}没有找到Celery worker进程${NC}"

# 停止Celery Beat
echo -e "${YELLOW}正在停止Celery Beat...${NC}"
pkill -f "celery beat" || echo -e "${RED}没有找到Celery beat进程${NC}"

# 检查是否有任何Celery进程还在运行
sleep 2
CELERY_PROCS=$(pgrep -f "celery")

if [ -n "$CELERY_PROCS" ]; then
    echo -e "${YELLOW}仍然有一些Celery进程在运行，尝试强制终止...${NC}"
    pkill -9 -f "celery"
    echo -e "${GREEN}所有Celery进程已强制终止${NC}"
else
    echo -e "${GREEN}所有Celery进程已正常停止${NC}"
fi

echo -e "${GREEN}Celery服务已停止!${NC}" 