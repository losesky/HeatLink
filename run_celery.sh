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

# 获取当前目录的绝对路径
CURRENT_DIR=$(pwd)
echo -e "${GREEN}当前目录: ${CURRENT_DIR}${NC}"

# 确保目录结构
if [ ! -d "backend/worker/asyncio_fix" ]; then
    echo -e "${YELLOW}创建异步修复目录...${NC}"
    mkdir -p backend/worker/asyncio_fix
fi

# 检查.env文件是否存在
if [ ! -f "backend/.env" ]; then
    echo -e "${RED}错误: 未找到环境配置文件 backend/.env${NC}"
    echo -e "${YELLOW}请确保backend/.env文件存在并包含必要的配置项，如DATABASE_URL和SECRET_KEY${NC}"
    exit 1
fi

# 检查虚拟环境
VENV_DIR="backend/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}未找到虚拟环境，创建中...${NC}"
    python3 -m venv $VENV_DIR
    source $VENV_DIR/bin/activate
    
    # 检查requirements.txt文件
    if [ -f "backend/requirements.txt" ]; then
        echo -e "${GREEN}安装依赖项...${NC}"
        pip install -r backend/requirements.txt
    else
        echo -e "${RED}警告: 未找到backend/requirements.txt文件，无法安装依赖项${NC}"
        echo -e "${YELLOW}请确保requirements.txt文件存在${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}激活虚拟环境...${NC}"
    source $VENV_DIR/bin/activate
fi

echo -e "${GREEN}设置环境变量...${NC}"
export PYTHONPATH=$CURRENT_DIR
# 将日志重定向设置为true
export CELERY_WORKER_REDIRECT_STDOUTS=true
export CELERY_WORKER_HIJACK_ROOT_LOGGER=true
export PYTHONUNBUFFERED=1
# 设置日志级别环境变量 - 使用INFO来实现良好的日志输出
export LOG_LEVEL=INFO

# 加载.env文件中的环境变量
if [ -f "backend/.env" ]; then
    echo -e "${GREEN}加载.env文件中的环境变量...${NC}"
    set -a
    source backend/.env
    set +a
fi

# 确保日志目录存在
mkdir -p logs

cd backend

echo -e "${GREEN}启动 Celery Worker...${NC}"
celery -A worker.celery_app worker --loglevel=info --concurrency=2 --logfile=${CURRENT_DIR}/logs/celery_worker.log --detach

# 如果上一个命令失败，则输出错误信息并退出
if [ $? -ne 0 ]; then
    echo -e "${RED}Celery Worker 启动失败!${NC}"
    exit 1
fi

echo -e "${GREEN}启动 Celery Beat...${NC}"
celery -A worker.celery_app beat --loglevel=info --logfile=${CURRENT_DIR}/logs/celery_beat.log --detach

# 如果上一个命令失败，则输出错误信息并退出
if [ $? -ne 0 ]; then
    echo -e "${RED}Celery Beat 启动失败!${NC}"
    exit 1
fi

# 启动专门处理news-queue的Worker
echo -e "${GREEN}启动 News Queue Worker...${NC}"
celery -A worker.celery_app worker --loglevel=info --concurrency=1 --queues=news-queue --hostname=news_worker@%h --logfile=${CURRENT_DIR}/logs/celery_news_worker.log --detach

# 如果上一个命令失败，则输出错误信息并退出
if [ $? -ne 0 ]; then
    echo -e "${RED}News Queue Worker 启动失败!${NC}"
    exit 1
fi

echo -e "${GREEN}Celery 服务已启动!${NC}"
echo "查看日志:"
echo "  - Worker: tail -f ${CURRENT_DIR}/logs/celery_worker.log"
echo "  - Beat: tail -f ${CURRENT_DIR}/logs/celery_beat.log"
echo "  - News Worker: tail -f ${CURRENT_DIR}/logs/celery_news_worker.log"
echo
echo -e "${YELLOW}使用 ./stop_celery.sh 停止服务${NC}" 