#!/bin/bash

# 设置颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 显示标题
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}   HeatLink 本地开发环境启动脚本   ${NC}"
echo -e "${GREEN}=======================================${NC}"

# 检查 Docker 和 Docker Compose 是否已安装
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker 未安装${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}错误: Docker Compose 未安装${NC}"
    exit 1
fi

# 复制本地环境配置文件
echo -e "${YELLOW}正在准备本地开发环境配置...${NC}"
cp .env.local .env

# 启动数据库和缓存服务
echo -e "${YELLOW}正在启动数据库和缓存服务...${NC}"
docker-compose -f docker-compose.local.yml up -d

# 等待服务启动
echo -e "${YELLOW}等待服务启动...${NC}"
sleep 5

# 运行数据库迁移
echo -e "${YELLOW}运行数据库迁移...${NC}"
cd backend
# 检查是否有迁移文件
if [ -z "$(ls -A alembic/versions/)" ]; then
    echo -e "${YELLOW}创建初始迁移文件...${NC}"
    alembic revision --autogenerate -m "Initial migration"
fi
echo -e "${YELLOW}应用迁移...${NC}"
alembic upgrade head

# 显示启动信息
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}本地开发环境已准备就绪!${NC}"
echo -e "${GREEN}=======================================${NC}"
echo -e "现在您可以在不同的终端窗口中运行以下命令:"
echo -e ""
echo -e "${YELLOW}启动后端API服务:${NC}"
echo -e "cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000"
echo -e ""
echo -e "${YELLOW}启动Celery Worker:${NC}"
echo -e "cd backend && python worker_start.py"
echo -e ""
echo -e "${YELLOW}启动Celery Beat:${NC}"
echo -e "cd backend && python beat_start.py"
echo -e ""
echo -e "${GREEN}=======================================${NC}"
echo -e "服务访问地址:"
echo -e "API: ${YELLOW}http://localhost:8000${NC}"
echo -e "API 文档: ${YELLOW}http://localhost:8000/api/docs${NC}"
echo -e "PgAdmin: ${YELLOW}http://localhost:5050${NC}"
echo -e "  - 邮箱: ${YELLOW}admin@heatlink.com${NC}"
echo -e "  - 密码: ${YELLOW}admin${NC}"
echo -e "Redis Commander: ${YELLOW}http://localhost:8081${NC}"
echo -e "${GREEN}=======================================${NC}"
echo -e "停止环境: ${YELLOW}docker-compose -f docker-compose.local.yml down${NC}"
echo -e "${GREEN}=======================================${NC}" 