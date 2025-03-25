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

# 检查是否存在Celery进程
CELERY_PROCS=$(ps aux | grep "celery" | grep -v grep | wc -l)

if [ $CELERY_PROCS -eq 0 ]; then
    echo -e "${YELLOW}未发现运行中的Celery进程${NC}"
    exit 0
fi

echo -e "${GREEN}发现 $CELERY_PROCS 个Celery进程:${NC}"
ps aux | grep "celery" | grep -v grep

echo -e "${YELLOW}正在停止Celery进程...${NC}"

# 停止所有Celery进程
pkill -f "celery -A worker.celery_app worker"
pkill -f "celery -A worker.celery_app beat"

# 等待进程终止
sleep 2

# 检查是否还有残留进程
CELERY_PROCS=$(ps aux | grep "celery" | grep -v grep | wc -l)
if [ $CELERY_PROCS -gt 0 ]; then
    echo -e "${YELLOW}仍有 $CELERY_PROCS 个进程存在，尝试使用SIGKILL强制终止...${NC}"
    pkill -9 -f "celery"
    sleep 1
fi

# 最终检查
CELERY_PROCS=$(ps aux | grep "celery" | grep -v grep | wc -l)
if [ $CELERY_PROCS -eq 0 ]; then
    echo -e "${GREEN}所有Celery进程已成功停止${NC}"
else
    echo -e "${RED}警告: 仍有 $CELERY_PROCS 个Celery进程未能停止${NC}"
    ps aux | grep "celery" | grep -v grep
fi

# 清理PID文件
if [ -f "celery.pid" ]; then
    rm celery.pid
    echo -e "${GREEN}已移除celery.pid文件${NC}"
fi 