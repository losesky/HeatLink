#!/bin/bash

# 设置颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 显示标题
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}   HeatLink 开发环境启动脚本   ${NC}"
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

# 复制开发环境配置文件
echo -e "${YELLOW}正在准备开发环境配置...${NC}"
cp .env.dev .env

# 构建并启动开发环境容器
echo -e "${YELLOW}正在启动开发环境容器...${NC}"
docker-compose -f docker-compose.dev.yml up -d --build

# 显示容器状态
echo -e "${YELLOW}容器状态:${NC}"
docker-compose -f docker-compose.dev.yml ps

# 显示访问信息
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}开发环境已启动!${NC}"
echo -e "${GREEN}=======================================${NC}"
echo -e "API: ${YELLOW}http://localhost:8000${NC}"
echo -e "API 文档: ${YELLOW}http://localhost:8000/api/docs${NC}"
echo -e "PgAdmin: ${YELLOW}http://localhost:5050${NC}"
echo -e "  - 邮箱: ${YELLOW}admin@heatlink.com${NC}"
echo -e "  - 密码: ${YELLOW}admin${NC}"
echo -e "Redis Commander: ${YELLOW}http://localhost:8081${NC}"
echo -e "${GREEN}=======================================${NC}"
echo -e "查看日志: ${YELLOW}docker-compose -f docker-compose.dev.yml logs -f${NC}"
echo -e "停止环境: ${YELLOW}docker-compose -f docker-compose.dev.yml down${NC}"
echo -e "${GREEN}=======================================${NC}" 