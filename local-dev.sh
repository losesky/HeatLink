#!/bin/bash

# 设置颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 显示标题
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}   HeatLink 本地开发环境启动脚本   ${NC}"
echo -e "${GREEN}=======================================${NC}"

# 功能：检查命令执行状态
check_status() {
    if [ $? -ne 0 ]; then
        echo -e "${RED}$1${NC}"
        exit 1
    fi
}

# 功能：等待服务就绪 - 增强版
wait_for_service() {
    local service_name=$1
    local check_command=$2
    local max_attempts=$3
    local sleep_time=$4
    local attempt=1

    echo -e "${YELLOW}等待 ${service_name} 就绪...${NC}"
    
    while [ $attempt -le $max_attempts ]; do
        echo -e "${YELLOW}  尝试 $attempt/$max_attempts${NC}"
        
        # 执行检查命令
        if eval $check_command; then
            echo -e "${GREEN}  ${service_name} 已就绪!${NC}"
            return 0
        fi
        
        echo -e "${YELLOW}  等待 ${sleep_time} 秒后重试...${NC}"
        sleep $sleep_time
        attempt=$((attempt+1))
    done
    
    echo -e "${RED}${service_name} 未能在规定时间内就绪${NC}"
    return 1
}

# 创建初始化数据的函数
init_data() {
    echo -e "${YELLOW}执行数据初始化...${NC}"
    
    # 创建一个临时Python脚本文件
    cat > .temp_init_data.py << EOF
#!/usr/bin/env python
import os
import sys
import traceback
import asyncio

# 添加项目根目录和脚本目录到Python路径
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('./scripts'))

try:
    # 加载模块之前打印调试信息
    print(f'当前目录: {os.getcwd()}')
    print(f'Python路径: {sys.path}')
    
    # 使用try/except单独处理每个导入
    try:
        from scripts.init_sources import init_db as init_sources
        print('成功导入初始化源模块')
    except Exception as e:
        print(f'导入初始化源模块失败: {str(e)}')
        traceback.print_exc()
        sys.exit(1)
        
    try:
        from scripts.init_tags import init_tags
        print('成功导入初始化标签模块')
    except Exception as e:
        print(f'导入初始化标签模块失败: {str(e)}')
        traceback.print_exc()
        sys.exit(1)
        
    try:
        from scripts.create_admin import create_admin_auto
        print('成功导入创建管理员模块')
    except Exception as e:
        print(f'导入创建管理员模块失败: {str(e)}')
        traceback.print_exc()
        sys.exit(1)
    
    # 导入代理初始化模块
    try:
        from scripts.init_proxy import init_proxy
        print('成功导入代理初始化模块')
    except Exception as e:
        print(f'导入代理初始化模块失败: {str(e)}')
        traceback.print_exc()
        sys.exit(1)
    
    # 初始化新闻源
    print('初始化新闻源...')
    init_sources()
    
    # 初始化标签
    print('初始化标签...')
    init_tags()
    
    # 自动创建管理员用户（非交互模式）
    print('创建默认管理员用户...')
    create_admin_auto(email='admin@example.com', password='adminpassword')
    
    # 初始化代理配置
    print('初始化代理配置...')
    asyncio.run(init_proxy())
    
    print('数据初始化完成')
except Exception as e:
    print(f'初始化数据时出错: {str(e)}')
    traceback.print_exc()
    sys.exit(1)
EOF
    
    # 执行临时脚本
    python .temp_init_data.py
    init_result=$?
    
    # 删除临时脚本
    rm -f .temp_init_data.py
    
    return $init_result
}

# 检查环境依赖
check_dependencies() {
    # 检查 Docker 是否已安装
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}错误: Docker 未安装${NC}"
        exit 1
    fi

    # 检查 Docker Compose 可用性 - 使用新的子命令语法
    if ! docker compose version &> /dev/null; then
        echo -e "${RED}错误: Docker Compose 不可用${NC}"
        exit 1
    fi
}

# 准备环境配置
prepare_environment() {
    # 复制本地环境配置文件
    echo -e "${YELLOW}正在准备本地开发环境配置...${NC}"
    cp .env.local .env
    check_status "复制环境配置文件失败"

    # 创建数据备份目录
    BACKUP_DIR="db_backups"
    if [ ! -d "$BACKUP_DIR" ]; then
        mkdir -p "$BACKUP_DIR"
        echo -e "${YELLOW}创建数据备份目录: $BACKUP_DIR${NC}"
    fi
}

# 备份数据
backup_database() {
    # 检查是否存在运行中的容器
    if docker ps -q --filter "name=postgres-local" | grep -q .; then
        echo -e "${YELLOW}检测到已运行的数据库容器，执行数据备份...${NC}"
        BACKUP_FILE="$BACKUP_DIR/heatlink_backup_$(date +%Y%m%d_%H%M%S).sql"
        docker exec -t postgres-local pg_dump -U postgres -d heatlink_dev > "$BACKUP_FILE"
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}数据库备份已保存到: $BACKUP_FILE${NC}"
        else
            echo -e "${YELLOW}数据库备份失败，将继续但不保证数据安全${NC}"
        fi
    else
        echo -e "${YELLOW}未检测到运行中的数据库容器，跳过备份...${NC}"
    fi
}

# 启动容器
start_containers() {
    # 确保所有容器都已停止
    echo -e "${YELLOW}确保所有容器都干净重启...${NC}"
    docker compose -f docker-compose.local.yml down
    sleep 3  # 增加等待时间确保所有容器都已停止

    # 启动数据库和缓存服务
    echo -e "${YELLOW}正在启动数据库和缓存服务...${NC}"
    docker compose -f docker-compose.local.yml up -d
    check_status "启动容器服务失败"

    # 等待服务启动 - 使用更可靠的方式进行健康检查
    echo -e "${YELLOW}等待服务启动...${NC}"
    MAX_RETRIES=20  # 增加最大尝试次数
    RETRY_COUNT=0
    RETRY_DELAY=5   # 增加每次尝试的等待时间

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if docker ps | grep -q "postgres-local" && docker ps | grep -q "(healthy)"; then
            echo -e "${GREEN}所有服务已启动并健康${NC}"
            # 额外等待确保数据库完全就绪 - 新增
            echo -e "${YELLOW}额外等待5秒确保数据库完全就绪...${NC}"
            sleep 5
            break
        fi
        
        echo -e "${YELLOW}等待服务启动，尝试 $((RETRY_COUNT+1))/$MAX_RETRIES...${NC}"
        RETRY_COUNT=$((RETRY_COUNT+1))
        sleep $RETRY_DELAY
    done

    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        echo -e "${RED}服务启动超时，请手动检查容器状态${NC}"
        echo -e "${RED}终止执行...${NC}"
        exit 1
    fi
}

# 停止容器
stop_containers() {
    echo -e "${YELLOW}正在停止所有容器...${NC}"
    docker compose -f docker-compose.local.yml down
    check_status "停止容器失败"
    echo -e "${GREEN}所有容器已停止${NC}"
}

# 重置容器和数据
reset_containers() {
    echo -e "${YELLOW}正在重置所有容器和数据卷...${NC}"
    docker compose -f docker-compose.local.yml down -v
    check_status "重置容器和数据卷失败"
    echo -e "${GREEN}所有容器和数据卷已重置${NC}"
}

# 初始化和迁移数据库
initialize_database() {
    # 运行数据库初始化和迁移
    echo -e "${YELLOW}运行数据库初始化和迁移...${NC}"
    cd backend || { echo -e "${RED}找不到backend目录${NC}"; exit 1; }

    # 检查数据库
    echo -e "${YELLOW}检查数据库连接...${NC}"
    python -c "
import psycopg2
import time
import os
import json
from dotenv import load_dotenv

load_dotenv()

# 获取数据库连接信息
db_url = os.getenv('DATABASE_URL')
if not db_url:
    print('无法获取数据库连接信息，请检查.env文件')
    exit(1)

# 解析连接字符串
db_info = db_url.replace('postgresql://', '')
user_pass, host_db = db_info.split('@')
user, password = user_pass.split(':')
host_port, db = host_db.split('/')
host, port = host_port.split(':')

# 重试连接
max_retries = 15  # 增加重试次数
retry_delay = 5   # 增加重试间隔
connected = False

for i in range(max_retries):
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=db
        )
        # 检查是否能执行查询
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        conn.close()
        connected = True
        print('数据库连接成功!')
        break
    except Exception as e:
        print(f'尝试 {i+1}/{max_retries}: 连接数据库失败: {str(e)}')
        if i < max_retries - 1:
            print(f'等待 {retry_delay} 秒后重试...')
            time.sleep(retry_delay)

if not connected:
    print('无法连接到数据库，请检查数据库服务是否正常运行')
    exit(1)

# 将连接信息保存到临时文件，供后续脚本使用
connection_info = {
    'host': host,
    'port': port,
    'user': user,
    'password': password,
    'dbname': db
}
with open('.db_connection.json', 'w') as f:
    json.dump(connection_info, f)
"

    if [ $? -ne 0 ]; then
        echo -e "${RED}数据库连接失败，请检查数据库服务${NC}"
        exit 1
    fi

    # 检查migrations版本目录
    if [ ! -d "alembic/versions" ]; then
        echo -e "${YELLOW}创建migrations版本目录...${NC}"
        mkdir -p alembic/versions
    fi

    # 安全的迁移逻辑
    # 首先检查数据库是否已有alembic_version表
    echo -e "${YELLOW}检查迁移状态...${NC}"
    python -c "
import os
import json
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# 从临时文件加载连接信息
with open('.db_connection.json', 'r') as f:
    conn_info = json.load(f)

# 连接到数据库
try:
    conn = psycopg2.connect(
        host=conn_info['host'],
        port=conn_info['port'],
        user=conn_info['user'],
        password=conn_info['password'],
        dbname=conn_info['dbname']
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    
    # 检查alembic_version表是否存在
    cursor = conn.cursor()
    cursor.execute(\"\"\"
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'alembic_version'
        );
    \"\"\")
    table_exists = cursor.fetchone()[0]
    
    # 检查数据库是否已有数据表
    cursor.execute(\"\"\"
        SELECT COUNT(*) FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_type = 'BASE TABLE';
    \"\"\")
    table_count = cursor.fetchone()[0]
    
    # 输出信息供脚本使用
    with open('.migration_status.txt', 'w') as f:
        f.write(f'TABLE_EXISTS={table_exists}\\n')
        f.write(f'TABLE_COUNT={table_count}\\n')
    
    cursor.close()
    conn.close()
    
    if table_exists:
        print('已有迁移记录')
    else:
        if table_count > 0:
            print('数据库已有表但无迁移记录，需要特殊处理')
        else:
            print('全新数据库，需要初始化迁移')
            
except Exception as e:
    print(f'检查迁移状态失败: {str(e)}')
    exit(1)
"

    if [ $? -ne 0 ]; then
        echo -e "${RED}检查迁移状态失败${NC}"
        exit 1
    fi

    # 读取迁移状态
    source .migration_status.txt

    # 检查是否有迁移文件
    if [ -z "$(ls -A alembic/versions/)" ]; then
        echo -e "${YELLOW}创建初始迁移文件...${NC}"
        alembic revision --autogenerate -m "Initial migration"
        check_status "创建迁移文件失败"
    fi

    # 根据迁移状态决定如何处理
    if [ "$TABLE_EXISTS" = "True" ]; then
        echo -e "${YELLOW}应用增量迁移...${NC}"
        alembic upgrade head
        MIGRATION_STATUS=$?
    elif [ "$TABLE_COUNT" -gt "0" ]; then
        echo -e "${YELLOW}检测到现有数据库表但无迁移记录，标记当前版本...${NC}"
        alembic stamp head
        MIGRATION_STATUS=$?
    else
        echo -e "${YELLOW}应用全新迁移...${NC}"
        # 使用set +e允许命令失败不终止脚本
        set +e
        alembic upgrade head
        MIGRATION_STATUS=$?
        set -e
    fi

    # 处理迁移失败的情况
    if [ $MIGRATION_STATUS -ne 0 ]; then
        echo -e "${RED}数据库迁移过程中出现错误${NC}"
        echo -e "${YELLOW}尝试创建初始数据库结构...${NC}"
        
        # 创建数据库中的表结构
        python -c "
import os
import sys
import json
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import time

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath('.'))

# 加载环境变量
load_dotenv()

# 从models导入所有模型以确保它们被注册
try:
    from app.db.session import Base
    from app.models import *
except ImportError as e:
    print(f'导入模型失败: {str(e)}')
    sys.exit(1)

# 获取数据库连接
try:
    from app.core.config import settings
    engine = create_engine(settings.DATABASE_URL)

    # 创建所有表
    Base.metadata.create_all(engine)
    print('成功创建所有数据库表!')
    sys.exit(0)
except Exception as e:
    print(f'创建表时出错: {str(e)}')
    sys.exit(1)
"
        
        if [ $? -ne 0 ]; then
            echo -e "${RED}无法创建数据库表结构${NC}"
            exit 1
        else
            echo -e "${GREEN}成功创建数据库表结构${NC}"
            # 标记当前迁移状态
            echo -e "${YELLOW}标记当前数据库版本...${NC}"
            alembic stamp head
            check_status "标记数据库版本失败"
        fi
    else
        echo -e "${GREEN}数据库迁移成功完成${NC}"
    fi

    # 在继续之前再次等待数据库 - 新增
    echo -e "${YELLOW}确保数据库完全可用...${NC}"
    sleep 3

    # 执行数据初始化 - 使用我们的函数
    echo -e "${YELLOW}开始初始化数据...${NC}"
    if [ -d "scripts" ]; then
        init_data
        
        if [ $? -ne 0 ]; then
            echo -e "${RED}初始化数据失败${NC}"
            exit 1
        else
            echo -e "${GREEN}基础数据初始化成功${NC}"
        fi
    else
        echo -e "${RED}找不到初始化脚本目录: scripts/${NC}"
        exit 1
    fi

    # 清理临时文件
    rm -f .db_connection.json .migration_status.txt .data_status.json

    # 回到项目根目录
    cd ..
}

# 显示服务信息
show_service_info() {
    echo -e "${GREEN}=======================================${NC}"
    echo -e "${GREEN}本地开发环境信息${NC}"
    echo -e "${GREEN}=======================================${NC}"
    echo -e "可在不同的终端窗口中运行以下命令:"
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
}

# 显示容器状态
show_container_status() {
    echo -e "${YELLOW}当前运行的容器状态:${NC}"
    docker ps
    echo -e "${GREEN}=======================================${NC}"
}

# 完整初始化流程
full_initialization() {
    prepare_environment
    backup_database
    start_containers
    initialize_database
    show_service_info
}

# 显示标题
show_header() {
    clear
    echo -e "${GREEN}=======================================${NC}"
    echo -e "${GREEN}   HeatLink 本地开发环境管理菜单   ${NC}"
    echo -e "${GREEN}=======================================${NC}"
}

# 主菜单
show_menu() {
    show_header
    echo -e "请选择操作:"
    echo -e "${BLUE}1)${NC} 完整初始化开发环境 (启动容器+初始化数据)"
    echo -e "${BLUE}2)${NC} 启动所有容器"
    echo -e "${BLUE}3)${NC} 停止所有容器"
    echo -e "${BLUE}4)${NC} 重置所有容器和数据 (删除所有数据)"
    echo -e "${BLUE}5)${NC} 仅初始化/更新数据库 (容器已启动)"
    echo -e "${BLUE}6)${NC} 查看当前容器状态"
    echo -e "${BLUE}7)${NC} 显示服务访问信息"
    echo -e "${BLUE}8)${NC} 备份当前数据库"
    echo -e "${BLUE}0)${NC} 退出"
    echo -e "${GREEN}=======================================${NC}"
    echo -ne "请输入选项 [0-8]: "
    read -r choice
}

# 主程序
main() {
    # 检查依赖
    check_dependencies

    while true; do
        show_menu
        case $choice in
            1)
                echo -e "${YELLOW}启动完整初始化流程...${NC}"
                full_initialization
                echo -e "${GREEN}完整初始化完成!${NC}"
                read -p "按Enter键继续..."
                ;;
            2)
                echo -e "${YELLOW}启动所有容器...${NC}"
                start_containers
                echo -e "${GREEN}容器已启动!${NC}"
                read -p "按Enter键继续..."
                ;;
            3)
                echo -e "${YELLOW}停止所有容器...${NC}"
                stop_containers
                echo -e "${GREEN}容器已停止!${NC}"
                read -p "按Enter键继续..."
                ;;
            4)
                echo -e "${RED}警告: 此操作将删除所有数据!${NC}"
                read -p "确定要继续吗? (y/n): " confirm
                if [[ $confirm == [yY] || $confirm == [yY][eE][sS] ]]; then
                    reset_containers
                    echo -e "${GREEN}容器和数据已重置!${NC}"
                else
                    echo -e "${YELLOW}已取消操作${NC}"
                fi
                read -p "按Enter键继续..."
                ;;
            5)
                echo -e "${YELLOW}仅初始化/更新数据库...${NC}"
                initialize_database
                echo -e "${GREEN}数据库初始化/更新完成!${NC}"
                read -p "按Enter键继续..."
                ;;
            6)
                show_container_status
                read -p "按Enter键继续..."
                ;;
            7)
                show_service_info
                read -p "按Enter键继续..."
                ;;
            8)
                echo -e "${YELLOW}备份当前数据库...${NC}"
                backup_database
                echo -e "${GREEN}备份完成!${NC}"
                read -p "按Enter键继续..."
                ;;
            0)
                echo -e "${GREEN}感谢使用 HeatLink 本地开发环境管理工具!${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}无效选项，请重新输入${NC}"
                read -p "按Enter键继续..."
                ;;
        esac
    done
}

# 执行主程序
main 