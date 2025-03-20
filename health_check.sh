#!/bin/bash

# 设置颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 显示标题
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}   HeatLink 服务健康检查脚本   ${NC}"
echo -e "${GREEN}=======================================${NC}"

# 检查API服务
echo -e "${YELLOW}检查API服务...${NC}"
API_RESPONSE=$(curl -s http://localhost:8000/health)
if [ $? -eq 0 ]; then
    API_STATUS=$(echo $API_RESPONSE | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    if [ "$API_STATUS" == "ok" ]; then
        echo -e "${GREEN}API服务正常运行${NC}"
    else
        echo -e "${RED}API服务状态异常: $API_STATUS${NC}"
    fi
else
    echo -e "${RED}无法连接到API服务${NC}"
fi

# 检查详细健康状态
echo -e "\n${YELLOW}检查详细健康状态...${NC}"
HEALTH_RESPONSE=$(curl -s http://localhost:8000/api/health)
if [ $? -eq 0 ]; then
    # 提取状态信息
    HEALTH_STATUS=$(echo $HEALTH_RESPONSE | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)
    DB_STATUS=$(echo $HEALTH_RESPONSE | grep -o '"database":{"status":"[^"]*"' | cut -d'"' -f6)
    REDIS_STATUS=$(echo $HEALTH_RESPONSE | grep -o '"redis":{"status":"[^"]*"' | cut -d'"' -f6)
    
    echo -e "总体状态: $([ "$HEALTH_STATUS" == "healthy" ] && echo "${GREEN}$HEALTH_STATUS${NC}" || echo "${RED}$HEALTH_STATUS${NC}")"
    echo -e "数据库状态: $([ "$DB_STATUS" == "ok" ] && echo "${GREEN}$DB_STATUS${NC}" || echo "${RED}$DB_STATUS${NC}")"
    echo -e "Redis状态: $([ "$REDIS_STATUS" == "ok" ] && echo "${GREEN}$REDIS_STATUS${NC}" || echo "${RED}$REDIS_STATUS${NC}")"
    
    # 如果有错误，显示错误信息
    if [ "$DB_STATUS" != "ok" ]; then
        DB_ERROR=$(echo $HEALTH_RESPONSE | grep -o '"database":{[^}]*}' | grep -o '"error":"[^"]*"' | cut -d'"' -f4)
        echo -e "${RED}数据库错误: $DB_ERROR${NC}"
    fi
    
    if [ "$REDIS_STATUS" != "ok" ]; then
        REDIS_ERROR=$(echo $HEALTH_RESPONSE | grep -o '"redis":{[^}]*}' | grep -o '"error":"[^"]*"' | cut -d'"' -f4)
        echo -e "${RED}Redis错误: $REDIS_ERROR${NC}"
    fi
else
    echo -e "${RED}无法获取详细健康状态${NC}"
fi

# 检查Celery进程
echo -e "\n${YELLOW}检查Celery进程...${NC}"
CELERY_WORKER_COUNT=$(ps aux | grep "[c]elery -A worker.celery_app worker" | wc -l)
CELERY_BEAT_COUNT=$(ps aux | grep "[c]elery -A worker.celery_app beat" | wc -l)

if [ $CELERY_WORKER_COUNT -gt 0 ]; then
    echo -e "${GREEN}Celery Worker进程正在运行 ($CELERY_WORKER_COUNT 个)${NC}"
else
    echo -e "${RED}Celery Worker进程未运行${NC}"
fi

if [ $CELERY_BEAT_COUNT -gt 0 ]; then
    echo -e "${GREEN}Celery Beat进程正在运行 ($CELERY_BEAT_COUNT 个)${NC}"
else
    echo -e "${RED}Celery Beat进程未运行${NC}"
fi

# 显示结束信息
echo -e "\n${GREEN}=======================================${NC}"
echo -e "${YELLOW}健康检查完成${NC}"
echo -e "${GREEN}=======================================${NC}" 