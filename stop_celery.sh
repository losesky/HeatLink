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

# 更精确地检测真正的Celery进程，排除脚本本身
echo -e "${YELLOW}检查Celery进程...${NC}"

# 查找Celery worker进程
CELERY_WORKERS=$(ps aux | grep "[c]elery -A worker.celery_app worker" | wc -l)
if [ "$CELERY_WORKERS" -gt 0 ]; then
    echo -e "${GREEN}找到 $CELERY_WORKERS 个Celery worker进程${NC}"
    echo -e "${YELLOW}正在停止Celery worker进程...${NC}"
    pkill -f "celery -A worker.celery_app worker" || echo -e "${RED}无法停止Celery worker进程${NC}"
else
    echo -e "${YELLOW}未发现Celery worker进程${NC}"
fi

# 查找Celery beat进程
CELERY_BEAT=$(ps aux | grep "[c]elery -A worker.celery_app beat" | wc -l)
if [ "$CELERY_BEAT" -gt 0 ]; then
    echo -e "${GREEN}找到 $CELERY_BEAT 个Celery beat进程${NC}"
    echo -e "${YELLOW}正在停止Celery beat进程...${NC}"
    pkill -f "celery -A worker.celery_app beat" || echo -e "${RED}无法停止Celery beat进程${NC}"
else
    echo -e "${YELLOW}未发现Celery beat进程${NC}"
fi

# 等待进程停止
sleep 2

# 再次检查是否有真正的Celery进程存在
REMAINING_WORKERS=$(ps aux | grep "[c]elery -A worker.celery_app worker" | wc -l)
REMAINING_BEAT=$(ps aux | grep "[c]elery -A worker.celery_app beat" | wc -l)
TOTAL_REMAINING=$((REMAINING_WORKERS + REMAINING_BEAT))

if [ "$TOTAL_REMAINING" -gt 0 ]; then
    echo -e "${YELLOW}仍有 $TOTAL_REMAINING 个Celery进程在运行，尝试强制终止...${NC}"
    # 强制停止worker
    if [ "$REMAINING_WORKERS" -gt 0 ]; then
        pkill -9 -f "celery -A worker.celery_app worker"
    fi
    # 强制停止beat
    if [ "$REMAINING_BEAT" -gt 0 ]; then
        pkill -9 -f "celery -A worker.celery_app beat"
    fi
    echo -e "${GREEN}所有Celery进程已强制终止${NC}"
else
    echo -e "${GREEN}所有Celery进程已停止${NC}"
fi

# 检查是否还有遗漏的进程（可能有不同的命令行）
OTHER_CELERY=$(ps aux | grep "[c]elery" | grep -v "grep" | wc -l)
if [ "$OTHER_CELERY" -gt 0 ]; then
    echo -e "${YELLOW}发现 $OTHER_CELERY 个其他Celery进程，尝试停止...${NC}"
    ps aux | grep "[c]elery" | grep -v "grep"
    pkill -f "[c]elery"
    sleep 1
    # 检查是否还有残留进程
    STILL_RUNNING=$(ps aux | grep "[c]elery" | grep -v "grep" | wc -l)
    if [ "$STILL_RUNNING" -gt 0 ]; then
        echo -e "${RED}无法停止所有Celery进程，尝试强制终止...${NC}"
        pkill -9 -f "[c]elery"
    fi
fi

echo -e "${GREEN}Celery服务已停止!${NC}" 