#!/bin/bash

# 设置颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置选项（可通过环境变量覆盖）
API_HOST=${API_HOST:-"localhost"}
API_PORT=${API_PORT:-"8000"}
API_BASE_URL="http://${API_HOST}:${API_PORT}"

# 忽略终端相关警告
export TERM=xterm

# 显示标题
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}   HeatLink 服务健康检查脚本   ${NC}"
echo -e "${GREEN}=======================================${NC}"

# 检测环境
echo -e "\n${YELLOW}检测运行环境...${NC}"

# 检查是否在Docker中运行
IN_DOCKER=false
if [ -f /.dockerenv ] || grep -q docker /proc/1/cgroup 2>/dev/null; then
    IN_DOCKER=true
    echo -e "${BLUE}运行环境: Docker 容器${NC}"
else
    echo -e "${BLUE}运行环境: 主机系统${NC}"
fi

# 显示主机名和系统信息
HOSTNAME=$(hostname 2>/dev/null)
if [ -n "$HOSTNAME" ]; then
    echo -e "${BLUE}主机名: $HOSTNAME${NC}"
fi

OS_INFO=$(cat /etc/os-release 2>/dev/null | grep "PRETTY_NAME" | cut -d= -f2 | tr -d '"')
if [ -n "$OS_INFO" ]; then
    echo -e "${BLUE}操作系统: $OS_INFO${NC}"
fi

KERNEL=$(uname -r 2>/dev/null)
if [ -n "$KERNEL" ]; then
    echo -e "${BLUE}内核版本: $KERNEL${NC}"
fi

# 显示API信息
echo -e "${BLUE}API端点: ${API_BASE_URL}${NC}"

# 检查API服务
echo -e "\n${YELLOW}检查API服务...${NC}"
API_RESPONSE=$(curl -s -m 5 ${API_BASE_URL}/health 2>/dev/null)
API_EXIT_CODE=$?

if [ $API_EXIT_CODE -eq 0 ]; then
    API_STATUS=$(echo $API_RESPONSE | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    if [ "$API_STATUS" == "ok" ]; then
        echo -e "${GREEN}API服务正常运行${NC}"
    else
        echo -e "${RED}API服务状态异常: $API_STATUS${NC}"
    fi
else
    echo -e "${RED}无法连接到API服务 (${API_BASE_URL}/health)${NC}"
    echo -e "${YELLOW}可能的原因:${NC}"
    echo -e "  - API服务未运行"
    echo -e "  - 端口配置错误 (当前端口: ${API_PORT})"
    echo -e "  - 主机名配置错误 (当前主机: ${API_HOST})"
    echo -e "可通过设置环境变量调整配置: API_HOST=xxx API_PORT=xxx $0"
fi

# 检查详细健康状态
echo -e "\n${YELLOW}检查详细健康状态...${NC}"
HEALTH_RESPONSE=$(curl -s -m 5 ${API_BASE_URL}/api/health 2>/dev/null)
HEALTH_EXIT_CODE=$?

if [ $HEALTH_EXIT_CODE -eq 0 ]; then
    # 提取状态信息
    HEALTH_STATUS=$(echo $HEALTH_RESPONSE | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)
    DB_STATUS=$(echo $HEALTH_RESPONSE | grep -o '"database":{"status":"[^"]*"' | cut -d'"' -f6)
    REDIS_STATUS=$(echo $HEALTH_RESPONSE | grep -o '"redis":{"status":"[^"]*"' | cut -d'"' -f6)
    
    if [ -n "$HEALTH_STATUS" ]; then
        echo -e "总体状态: $([ "$HEALTH_STATUS" == "healthy" ] && echo "${GREEN}$HEALTH_STATUS${NC}" || echo "${RED}$HEALTH_STATUS${NC}")"
    else
        echo -e "总体状态: ${RED}未知${NC} (无法解析响应)"
    fi
    
    if [ -n "$DB_STATUS" ]; then
        echo -e "数据库状态: $([ "$DB_STATUS" == "ok" ] && echo "${GREEN}$DB_STATUS${NC}" || echo "${RED}$DB_STATUS${NC}")"
    else
        echo -e "数据库状态: ${RED}未知${NC} (无法解析响应)"
    fi
    
    if [ -n "$REDIS_STATUS" ]; then
        echo -e "Redis状态: $([ "$REDIS_STATUS" == "ok" ] && echo "${GREEN}$REDIS_STATUS${NC}" || echo "${RED}$REDIS_STATUS${NC}")"
    else
        echo -e "Redis状态: ${RED}未知${NC} (无法解析响应)"
    fi
    
    # 如果有错误，显示错误信息
    if [ "$DB_STATUS" != "ok" ]; then
        DB_ERROR=$(echo $HEALTH_RESPONSE | grep -o '"database":{[^}]*}' | grep -o '"error":"[^"]*"' | cut -d'"' -f4)
        if [ -n "$DB_ERROR" ]; then
            echo -e "${RED}数据库错误: $DB_ERROR${NC}"
        fi
    fi
    
    if [ "$REDIS_STATUS" != "ok" ]; then
        REDIS_ERROR=$(echo $HEALTH_RESPONSE | grep -o '"redis":{[^}]*}' | grep -o '"error":"[^"]*"' | cut -d'"' -f4)
        if [ -n "$REDIS_ERROR" ]; then
            echo -e "${RED}Redis错误: $REDIS_ERROR${NC}"
        fi
    fi
else
    echo -e "${RED}无法获取详细健康状态 (${API_BASE_URL}/api/health)${NC}"
    echo -e "${YELLOW}提示: API服务需要正常运行才能获取健康状态${NC}"
fi

# 检查Celery进程
echo -e "\n${YELLOW}检查Celery进程...${NC}"
CELERY_WORKER_COUNT=$(ps aux 2>/dev/null | grep "[c]elery -A worker.celery_app worker" | wc -l)
CELERY_BEAT_COUNT=$(ps aux 2>/dev/null | grep "[c]elery -A worker.celery_app beat" | wc -l)

if [ $CELERY_WORKER_COUNT -gt 0 ]; then
    echo -e "${GREEN}Celery Worker进程正在运行 ($CELERY_WORKER_COUNT 个)${NC}"
    # 显示具体的Worker进程
    WORKER_PROCS=$(ps -eo pid,etime,command 2>/dev/null | grep "[c]elery -A worker.celery_app worker" | awk '{print "  PID: " $1 ", 运行时间: " $2}')
    if [ -n "$WORKER_PROCS" ]; then
        echo -e "$WORKER_PROCS"
    fi
else
    echo -e "${RED}Celery Worker进程未运行${NC}"
fi

if [ $CELERY_BEAT_COUNT -gt 0 ]; then
    echo -e "${GREEN}Celery Beat进程正在运行 ($CELERY_BEAT_COUNT 个)${NC}"
    # 显示Beat进程运行时间
    BEAT_PROCS=$(ps -eo pid,etime,command 2>/dev/null | grep "[c]elery -A worker.celery_app beat" | awk '{print "  PID: " $1 ", 运行时间: " $2}')
    if [ -n "$BEAT_PROCS" ]; then
        echo -e "$BEAT_PROCS"
    fi
else
    echo -e "${RED}Celery Beat进程未运行${NC}"
fi

# 检查Redis服务
echo -e "\n${YELLOW}检查Redis服务...${NC}"
REDIS_RUNNING=$(ps aux 2>/dev/null | grep "[r]edis-server" | wc -l)
if [ $REDIS_RUNNING -gt 0 ]; then
    echo -e "${GREEN}Redis服务正在运行${NC}"
    
    # 如果redis-cli可用，获取更多信息
    REDIS_CLI=$(which redis-cli 2>/dev/null)
    if [ -n "$REDIS_CLI" ]; then
        # 尝试获取Redis信息
        REDIS_INFO=$($REDIS_CLI info 2>/dev/null | grep -E "redis_version|connected_clients|used_memory_human|total_connections_received")
        if [ -n "$REDIS_INFO" ]; then
            echo -e "${BLUE}Redis信息:${NC}"
            echo "$REDIS_INFO" | sed 's/^/  /'
        fi
    fi
else
    # 尝试通过redis-cli来检查
    REDIS_CLI=$(which redis-cli 2>/dev/null)
    if [ -n "$REDIS_CLI" ]; then
        REDIS_PING=$($REDIS_CLI ping 2>/dev/null)
        if [ "$REDIS_PING" == "PONG" ]; then
            echo -e "${GREEN}Redis服务正在运行${NC}"
        else
            echo -e "${RED}Redis服务可能未运行${NC}"
        fi
    else
        echo -e "${RED}无法检测Redis服务 (redis-cli不可用)${NC}"
    fi
fi

# 检查系统资源
echo -e "\n${YELLOW}检查系统资源...${NC}"
CPU_USAGE=$(top -bn1 2>/dev/null | grep "Cpu(s)" | awk '{print $2 + $4}')
if [ -z "$CPU_USAGE" ]; then
    CPU_USAGE="无法获取"
else
    CPU_USAGE="${CPU_USAGE}%"
fi

MEM_TOTAL=$(free -m 2>/dev/null | awk 'NR==2{print $2}')
MEM_USED=$(free -m 2>/dev/null | awk 'NR==2{print $3}')
if [ -n "$MEM_TOTAL" ] && [ -n "$MEM_USED" ] && [ "$MEM_TOTAL" -gt 0 ]; then
    MEM_USAGE=$(awk "BEGIN {printf \"%.2f\", ($MEM_USED*100/$MEM_TOTAL)}")"%"
    MEM_TOTAL_GB=$(awk "BEGIN {printf \"%.1f\", $MEM_TOTAL/1024}")
    MEM_USED_GB=$(awk "BEGIN {printf \"%.1f\", $MEM_USED/1024}")
    echo -e "内存使用率: $MEM_USAGE ($MEM_USED_GB GB / $MEM_TOTAL_GB GB)"
else
    echo -e "内存使用率: 无法获取"
fi

echo -e "CPU使用率: $CPU_USAGE"

# 检查磁盘空间
echo -e "\n${YELLOW}检查磁盘空间...${NC}"
DF_OUTPUT=$(df -h / 2>/dev/null | grep -v "Filesystem")
if [ -n "$DF_OUTPUT" ]; then
    echo "$DF_OUTPUT" | awk '{print "根目录使用情况: " $5 " (可用: " $4 ", 总量: " $2 ")"}'
else
    echo -e "${RED}无法获取磁盘空间信息${NC}"
fi

# 检查网络连接
echo -e "\n${YELLOW}检查网络连接...${NC}"
NETSTAT_CMD=$(which netstat 2>/dev/null)
if [ -n "$NETSTAT_CMD" ]; then
    ESTABLISHED=$(netstat -nat 2>/dev/null | grep ESTABLISHED | wc -l)
    LISTEN=$(netstat -nat 2>/dev/null | grep LISTEN | wc -l)
    echo -e "活动连接: $ESTABLISHED 个"
    echo -e "监听端口: $LISTEN 个"
    
    # 检查常用端口
    echo -e "${BLUE}关键端口监听状态:${NC}"
    netstat -tuln 2>/dev/null | grep -E ":(80|8000|8080|6379|5432)" | awk '{print "  " $4}'
else
    echo -e "${RED}无法获取网络连接信息 (netstat不可用)${NC}"
fi

# 运行状态总结
echo -e "\n${YELLOW}系统状态总结:${NC}"
if [ "$API_EXIT_CODE" -eq 0 ] && [ "$HEALTH_STATUS" == "healthy" ]; then
    echo -e "${GREEN}✓ API服务正常${NC}"
else
    echo -e "${RED}✗ API服务异常${NC}"
fi

if [ "$DB_STATUS" == "ok" ]; then
    echo -e "${GREEN}✓ 数据库正常${NC}"
else
    echo -e "${RED}✗ 数据库异常${NC}"
fi

if [ "$REDIS_STATUS" == "ok" ] || [ $REDIS_RUNNING -gt 0 ]; then
    echo -e "${GREEN}✓ Redis正常${NC}"
else
    echo -e "${RED}✗ Redis异常${NC}"
fi

if [ $CELERY_WORKER_COUNT -gt 0 ]; then
    echo -e "${GREEN}✓ Celery Worker正常${NC}"
else
    echo -e "${RED}✗ Celery Worker异常${NC}"
fi

if [ $CELERY_BEAT_COUNT -gt 0 ]; then
    echo -e "${GREEN}✓ Celery Beat正常${NC}"
else
    echo -e "${RED}✗ Celery Beat异常${NC}"
fi

# 显示结束信息
echo -e "\n${GREEN}=======================================${NC}"
echo -e "${YELLOW}健康检查完成 - $(date)${NC}"
echo -e "${GREEN}=======================================${NC}" 