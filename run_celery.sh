#!/bin/bash

# 日志颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}     启动 Celery 服务     ${NC}"
echo -e "${BLUE}=====================================${NC}"

# 确保目录结构
if [ ! -d "backend/worker/asyncio_fix" ]; then
    echo -e "${YELLOW}创建异步修复目录...${NC}"
    mkdir -p backend/worker/asyncio_fix
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}未找到虚拟环境，创建中...${NC}"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo -e "${GREEN}设置环境变量...${NC}"
export PYTHONPATH=$(pwd)
# 设置环境变量以减少控制台输出
export CELERY_WORKER_REDIRECT_STDOUTS=true
export PYTHONUNBUFFERED=1
# 设置日志级别环境变量 - 使用ERROR来极大减少输出
export LOG_LEVEL=ERROR

cd backend

# 确保日志目录存在
mkdir -p ../logs

echo -e "${GREEN}启动 Celery Worker...${NC}"
celery -A worker.celery_app worker --loglevel=error --concurrency=2 --logfile=../logs/celery_worker.log --detach

echo -e "${GREEN}启动 Celery Beat...${NC}"
celery -A worker.celery_app beat --loglevel=error --logfile=../logs/celery_beat.log --detach

# 启动专门处理news-queue的Worker
echo -e "${GREEN}启动 News Queue Worker...${NC}"
celery -A worker.celery_app worker --loglevel=error --concurrency=1 --queues=news-queue --hostname=news_worker@%h --logfile=../logs/celery_news_worker.log --detach

echo -e "${GREEN}Celery 服务已启动!${NC}"
echo "查看日志:"
echo "  - Worker: tail -f logs/celery_worker.log"
echo "  - Beat: tail -f logs/celery_beat.log"
echo "  - News Worker: tail -f logs/celery_news_worker.log"
echo
echo -e "${YELLOW}使用 ./stop_celery.sh 停止服务${NC}" 