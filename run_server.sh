#!/bin/bash
# ===========================================
# HeatLink 后端服务启动脚本
# 本脚本用于方便地启动HeatLink的后端API服务
# ===========================================

# 设置颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # 恢复默认颜色

# 设置日志文件
LOG_DIR="logs"
mkdir -p $LOG_DIR
LOG_FILE="$LOG_DIR/server_$(date +%Y%m%d_%H%M%S).log"
PID_FILE=".server.pid"

# 显示标题
echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE}         HeatLink 后端服务启动脚本         ${NC}"
echo -e "${BLUE}=============================================${NC}"

# 解析命令行参数
ARGS=""
RELOAD=false
HOST="0.0.0.0"
PORT=8000
NO_CACHE=false
SYNC_ONLY=false

# 函数: 显示帮助信息
show_help() {
    echo -e "${GREEN}用法:${NC} $0 [选项]"
    echo
    echo -e "${GREEN}选项:${NC}"
    echo -e "  --help               显示此帮助信息"
    echo -e "  --reload             启用热重载功能（监控代码变更自动重启）"
    echo -e "  --host HOSTNAME      指定监听地址，默认为 0.0.0.0"
    echo -e "  --port PORT          指定监听端口，默认为 8000"
    echo -e "  --no-cache           禁用Redis缓存"
    echo -e "  --sync-only          仅同步数据库和源适配器，不启动服务"
    echo -e "  --clean-ports        启动前清理使用的端口"
    echo -e "  --no-chromedriver    禁用Chrome驱动清理"
    echo
    echo -e "${GREEN}示例:${NC}"
    echo -e "  $0 --reload --port 8080        使用热重载启动服务在8080端口"
    echo -e "  $0 --sync-only                 仅同步数据库不启动服务"
    exit 0
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --help)
            show_help
            ;;
        --reload)
            RELOAD=true
            ARGS="$ARGS --reload"
            shift
            ;;
        --host)
            HOST="$2"
            ARGS="$ARGS --host $2"
            shift 2
            ;;
        --port)
            PORT="$2"
            ARGS="$ARGS --port $2"
            shift 2
            ;;
        --no-cache)
            NO_CACHE=true
            ARGS="$ARGS --no-cache"
            shift
            ;;
        --sync-only)
            SYNC_ONLY=true
            ARGS="$ARGS --sync-only"
            shift
            ;;
        --clean-ports)
            ARGS="$ARGS --clean-ports"
            shift
            ;;
        --no-chromedriver)
            ARGS="$ARGS --no-chromedriver"
            shift
            ;;
        *)
            echo -e "${RED}错误: 未知参数 $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# 函数: 检查Python环境
check_python() {
    echo -e "${BLUE}[+] 检查Python环境...${NC}"
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}错误: 未找到python3命令${NC}"
        echo -e "${YELLOW}请确保已安装Python 3.9+${NC}"
        exit 1
    fi
    
    # 检查Python版本
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo -e "${GREEN}[√] 使用Python版本: $PY_VERSION${NC}"
    
    # 检查虚拟环境
    if [ -d "venv" ]; then
        echo -e "${BLUE}[+] 激活虚拟环境...${NC}"
        source venv/bin/activate
    elif [ -d "../venv" ]; then
        echo -e "${BLUE}[+] 激活上级目录虚拟环境...${NC}"
        source ../venv/bin/activate
    else
        echo -e "${YELLOW}[!] 未找到虚拟环境，使用系统Python${NC}"
    fi
}

# 函数: 检查依赖
check_dependencies() {
    echo -e "${BLUE}[+] 检查依赖项...${NC}"
    if [ ! -f "requirements.txt" ] && [ ! -f "backend/requirements.txt" ]; then
        echo -e "${YELLOW}[!] 未找到requirements.txt文件，跳过依赖检查${NC}"
        return
    fi
    
    REQ_FILE="requirements.txt"
    if [ ! -f "$REQ_FILE" ] && [ -f "backend/requirements.txt" ]; then
        REQ_FILE="backend/requirements.txt"
    fi
    
    # 简单检查几个核心依赖
    echo -e "${BLUE}[+] 检查核心依赖...${NC}"
    python3 -c "
try:
    import fastapi
    import uvicorn
    import sqlalchemy
    print('核心依赖检查通过')
except ImportError as e:
    print(f'缺少依赖: {e}')
    print('请运行: pip install -r $REQ_FILE')
    exit(1)
"
    if [ $? -ne 0 ]; then
        echo -e "${YELLOW}[!] 是否安装依赖? (y/n)${NC}"
        read -r answer
        if [[ "$answer" =~ ^[Yy]$ ]]; then
            echo -e "${BLUE}[+] 安装依赖...${NC}"
            pip install -r "$REQ_FILE"
        else
            echo -e "${YELLOW}[!] 跳过依赖安装，继续启动（可能会失败）${NC}"
        fi
    else
        echo -e "${GREEN}[√] 核心依赖检查通过${NC}"
    fi
}

# 函数: 检查环境变量
check_env() {
    echo -e "${BLUE}[+] 检查环境变量...${NC}"
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            echo -e "${YELLOW}[!] 未找到.env文件，但发现.env.example${NC}"
            echo -e "${YELLOW}[!] 是否要从.env.example创建.env? (y/n)${NC}"
            read -r answer
            if [[ "$answer" =~ ^[Yy]$ ]]; then
                cp .env.example .env
                echo -e "${GREEN}[√] 已创建.env文件，请根据需要编辑${NC}"
            else
                echo -e "${YELLOW}[!] 继续启动，但可能会出现配置问题${NC}"
            fi
        else
            echo -e "${RED}[!] 警告: 未找到.env文件，使用默认配置${NC}"
        fi
    else
        echo -e "${GREEN}[√] 找到.env文件${NC}"
    fi
}

# 函数: 检查服务器是否已在运行
check_running() {
    echo -e "${BLUE}[+] 检查服务是否已在运行...${NC}"
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null; then
            echo -e "${YELLOW}[!] 服务已在运行 (PID: $PID)${NC}"
            echo -e "${YELLOW}[!] 是否要终止并重新启动？ (y/n)${NC}"
            read -r answer
            if [[ "$answer" =~ ^[Yy]$ ]]; then
                echo -e "${BLUE}[+] 终止现有进程...${NC}"
                kill "$PID"
                sleep 2
                # 检查是否仍在运行
                if ps -p "$PID" > /dev/null; then
                    echo -e "${RED}[!] 无法终止进程，尝试强制终止${NC}"
                    kill -9 "$PID"
                    sleep 1
                fi
                rm -f "$PID_FILE"
            else
                echo -e "${RED}[!] 退出${NC}"
                exit 0
            fi
        else
            echo -e "${YELLOW}[!] 发现过期的PID文件，清理中...${NC}"
            rm -f "$PID_FILE"
        fi
    fi
}

# 函数: 启动服务器
start_server() {
    echo -e "${BLUE}[+] 正在启动后端服务...${NC}"
    echo -e "${BLUE}[+] 使用参数: $ARGS${NC}"
    
    if [ "$SYNC_ONLY" = true ]; then
        echo -e "${YELLOW}[!] 仅同步模式：不会启动API服务${NC}"
    else
        echo -e "${GREEN}[+] 启动服务: http://$HOST:$PORT${NC}"
    fi
    
    # 使用nohup运行服务器并将PID存储在文件中
    if [ "$RELOAD" = true ]; then
        echo -e "${YELLOW}[!] 热重载模式: 按Ctrl+C终止${NC}"
        python backend/start_server.py $ARGS 2>&1 | tee "$LOG_FILE"
    else
        echo -e "${GREEN}[+] 后台运行，日志输出到: $LOG_FILE${NC}"
        echo -e "${GREEN}[+] 使用 'tail -f $LOG_FILE' 查看日志${NC}"
        nohup python backend/start_server.py $ARGS > "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
        echo -e "${GREEN}[√] 服务已启动 (PID: $(cat "$PID_FILE"))${NC}"
    fi
}

# 主函数
main() {
    check_python
    check_dependencies
    check_env
    check_running
    start_server
    
    # 显示健康检查URL
    if [ "$SYNC_ONLY" = false ]; then
        echo -e "${BLUE}[+] 健康检查URL: http://$HOST:$PORT/health${NC}"
        echo -e "${BLUE}[+] API文档URL: http://$HOST:$PORT/docs${NC}"
    fi
    
    echo -e "${GREEN}[√] 启动流程完成${NC}"
}

# 异常处理
trap 'echo -e "${RED}[!] 脚本执行被中断${NC}"; exit 1' INT TERM

# 执行主函数
main

exit 0
