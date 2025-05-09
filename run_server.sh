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
ARCHIVE_DIR="${LOG_DIR}/archive"
mkdir -p $ARCHIVE_DIR
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
PUBLIC_ACCESS=false
CLEAN_LOGS=false

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
    echo -e "  --public             启用外部访问（配置CORS允许所有来源）"
    echo -e "  --clean-logs         启动前清理和压缩日志文件"
    echo
    echo -e "${GREEN}示例:${NC}"
    echo -e "  $0 --reload --port 8080        使用热重载启动服务在8080端口"
    echo -e "  $0 --public --port 8888        启用外部访问并使用8888端口"
    echo -e "  $0 --sync-only                 仅同步数据库不启动服务"
    echo -e "  $0 --clean-logs                启动前清理日志文件"
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
        --public)
            PUBLIC_ACCESS=true
            ARGS="$ARGS --public"
            shift
            ;;
        --clean-logs)
            CLEAN_LOGS=true
            shift
            ;;
        *)
            echo -e "${RED}错误: 未知参数 $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# 函数: 清理日志文件
clean_logs() {
    echo -e "${BLUE}[+] 清理日志文件...${NC}"
    
    # 日期标记
    DATE_TAG=$(date +%Y%m%d)
    
    # 压缩超过7天的日志文件
    echo -e "${YELLOW}[+] 查找并压缩超过7天的日志文件...${NC}"
    find "$LOG_DIR" -name "*.log" -type f -mtime +7 | while read -r log_file; do
        filename=$(basename "$log_file")
        echo -e "${GREEN}[+] 压缩: $filename${NC}"
        gzip -c "$log_file" > "${ARCHIVE_DIR}/${filename}.${DATE_TAG}.gz"
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}[+] 删除原始文件: $log_file${NC}"
            rm "$log_file"
        else
            echo -e "${RED}[!] 压缩失败，保留原始文件: $log_file${NC}"
        fi
    done
    
    # 删除超过30天的压缩日志
    echo -e "${YELLOW}[+] 删除超过30天的压缩日志...${NC}"
    find "$ARCHIVE_DIR" -name "*.gz" -type f -mtime +30 | while read -r old_log; do
        echo -e "${GREEN}[+] 删除旧压缩日志: $old_log${NC}"
        rm "$old_log"
    done
    
    # 压缩当前大于50MB的日志文件但不删除
    echo -e "${YELLOW}[+] 查找并压缩当前大于50MB的日志文件...${NC}"
    find "$LOG_DIR" -name "*.log" -type f -size +50M | while read -r large_log; do
        filename=$(basename "$large_log")
        echo -e "${GREEN}[+] 压缩大文件: $filename${NC}"
        cp "$large_log" "${ARCHIVE_DIR}/${filename}.${DATE_TAG}.copy"
        truncate -s 0 "$large_log"
        echo -e "[日志已于 $(date) 被清空以节省空间，完整日志已存档]" > "$large_log"
        gzip -c "${ARCHIVE_DIR}/${filename}.${DATE_TAG}.copy" > "${ARCHIVE_DIR}/${filename}.${DATE_TAG}.gz"
        rm "${ARCHIVE_DIR}/${filename}.${DATE_TAG}.copy"
    done
    
    # 显示当前日志使用情况
    echo -e "${GREEN}[+] 当前日志使用情况:${NC}"
    du -h "$LOG_DIR" | sort -hr | head -n 5
    
    echo -e "${GREEN}[√] 日志清理完成${NC}"
}

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
    
    # 如果开启了外部访问，提示将添加CORS配置
    if [ "$PUBLIC_ACCESS" = true ]; then
        echo -e "${YELLOW}[!] 已启用外部访问模式，将配置CORS允许所有来源${NC}"
        
        # 检查是否有公网IP，获取当前机器的IP地址
        if command -v ip &> /dev/null; then
            # Linux系统
            PUBLIC_IP=$(ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v "127.0.0.1" | head -n 1)
        elif command -v ifconfig &> /dev/null; then
            # macOS或其他Unix系统
            PUBLIC_IP=$(ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -n 1)
        else
            PUBLIC_IP="<无法获取IP>"
        fi
        
        echo -e "${GREEN}[+] 检测到本机IP地址: $PUBLIC_IP${NC}"
        echo -e "${GREEN}[+] API将可通过以下地址访问:${NC}"
        echo -e "${GREEN}   - http://$PUBLIC_IP:$PORT/api/docs${NC}"
        echo -e "${GREEN}   - http://$PUBLIC_IP:$PORT/docs${NC}"
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
    # 如果启用了日志清理，先执行清理
    if [ "$CLEAN_LOGS" = true ]; then
        clean_logs
    fi

    check_python
    check_dependencies
    check_env
    check_running
    start_server
    
    # 显示健康检查URL
    if [ "$SYNC_ONLY" = false ]; then
        echo -e "${BLUE}[+] 健康检查URL: http://$HOST:$PORT/health${NC}"
        echo -e "${BLUE}[+] API文档URL: http://$HOST:$PORT/docs${NC}"
        
        if [ "$PUBLIC_ACCESS" = true ]; then
            echo -e "${YELLOW}[!] 外部访问提示:${NC}"
            echo -e "${YELLOW}   - 确保端口 $PORT 在防火墙中已开放${NC}"
            echo -e "${YELLOW}   - 如使用云服务器，请在安全组中允许该端口${NC}"
            echo -e "${YELLOW}   - 如连接不成功，请检查防火墙和网络设置${NC}"
        fi
    fi
    
    # 提示可以使用日志清理功能
    if [ "$CLEAN_LOGS" = false ]; then
        echo -e "${YELLOW}[!] 提示: 使用 --clean-logs 参数可在启动前自动清理日志文件${NC}"
    fi
    
    echo -e "${GREEN}[√] 启动流程完成${NC}"
}

# 异常处理
trap 'echo -e "${RED}[!] 脚本执行被中断${NC}"; exit 1' INT TERM

# 执行主函数
main

exit 0
