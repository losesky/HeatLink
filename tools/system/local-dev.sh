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

# 功能：检查命令执行状态
check_status() {
    if [ $? -ne 0 ]; then
        echo -e "${RED}$1${NC}"
        exit 1
    fi
}

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

# 检查是否存在运行中的容器
if docker ps -q --filter "name=heatlink-postgres-local" | grep -q .; then
    echo -e "${YELLOW}检测到已运行的数据库容器，执行数据备份...${NC}"
    BACKUP_FILE="$BACKUP_DIR/heatlink_backup_$(date +%Y%m%d_%H%M%S).sql"
    docker exec -t heatlink-postgres-local pg_dump -U postgres -d heatlink_dev > "$BACKUP_FILE"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}数据库备份已保存到: $BACKUP_FILE${NC}"
    else
        echo -e "${YELLOW}数据库备份失败，将继续但不保证数据安全${NC}"
    fi
fi

# 启动数据库和缓存服务
echo -e "${YELLOW}正在启动数据库和缓存服务...${NC}"
docker compose -f docker-compose.local.yml up -d
check_status "启动容器服务失败"

# 等待服务启动 - 使用更可靠的方式进行健康检查
echo -e "${YELLOW}等待服务启动...${NC}"
MAX_RETRIES=10
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if docker ps | grep -q "heatlink-postgres-local" && docker ps | grep -q "(healthy)"; then
        echo -e "${GREEN}所有服务已启动并健康${NC}"
        break
    fi
    
    echo -e "${YELLOW}等待服务启动，尝试 $((RETRY_COUNT+1))/$MAX_RETRIES...${NC}"
    RETRY_COUNT=$((RETRY_COUNT+1))
    sleep 3
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo -e "${RED}服务启动超时，请手动检查容器状态${NC}"
    echo -e "${YELLOW}继续执行脚本，但可能会遇到连接问题${NC}"
fi

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
max_retries = 10
retry_delay = 3
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

# 创建一个更可靠的数据初始化检查函数
echo -e "${YELLOW}验证数据一致性...${NC}"
python -c "
import os
import sys
import json
import sqlalchemy
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect, MetaData

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath('.'))

# 加载环境变量
load_dotenv()

# 获取数据库连接
from app.core.config import settings
engine = create_engine(settings.DATABASE_URL)
inspector = inspect(engine)
metadata = MetaData()
metadata.reflect(bind=engine)

# 检查必要的表是否存在
required_tables = ['sources', 'categories', 'tags']
missing_tables = [t for t in required_tables if t not in inspector.get_table_names()]

if missing_tables:
    print(f'缺少必要的表: {missing_tables}')
    sys.exit(2)  # 特殊错误码 - 表缺失

# 检查sources表是否为空
try:
    with engine.connect() as conn:
        # 检查sources表
        if 'sources' in inspector.get_table_names():
            result = conn.execute(text('SELECT COUNT(*) FROM sources'))
            sources_count = result.scalar()
        else:
            sources_count = 0
            
        # 检查categories表
        if 'categories' in inspector.get_table_names():
            result = conn.execute(text('SELECT COUNT(*) FROM categories'))
            categories_count = result.scalar()
        else:
            categories_count = 0
            
        # 检查tags表
        if 'tags' in inspector.get_table_names():
            result = conn.execute(text('SELECT COUNT(*) FROM tags'))
            tags_count = result.scalar()
        else:
            tags_count = 0
        
    # 将计数信息写入文件以供bash脚本读取
    with open('.data_status.json', 'w') as f:
        json.dump({
            'sources_count': sources_count,
            'categories_count': categories_count,
            'tags_count': tags_count
        }, f)
        
    # 全面检查所有表
    if sources_count == 0 or categories_count == 0 or tags_count == 0:
        print('一个或多个核心表为空，需要初始化数据')
        sys.exit(1)  # 需要初始化
    else:
        print(f'数据检查: sources: {sources_count}, categories: {categories_count}, tags: {tags_count}')
        sys.exit(0)  # 不需要初始化
except Exception as e:
    print(f'检查数据时出错: {str(e)}')
    sys.exit(3)  # 特殊错误码 - 检查错误
"

DATA_STATUS=$?

# 根据数据验证结果处理数据初始化
if [ $DATA_STATUS -eq 1 ]; then
    echo -e "${YELLOW}需要初始化基础数据...${NC}"
    
    # 检查是否有init_all.py脚本
    if [ -f "scripts/init_all.py" ]; then
        # 执行初始化脚本
        echo -e "${YELLOW}运行数据初始化脚本...${NC}"
        # 修改为非交互模式
        python -c "
import os
import sys
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('./scripts'))

try:
    from scripts.init_sources import init_db as init_sources
    from scripts.init_tags import init_tags
    from scripts.create_admin import create_admin_auto
    
    # 初始化新闻源
    print('初始化新闻源...')
    init_sources()
    
    # 初始化标签
    print('初始化标签...')
    init_tags()
    
    # 自动创建管理员用户（非交互模式）
    print('创建默认管理员用户...')
    create_admin_auto(email='admin@example.com', password='adminpassword')
    
    print('数据初始化完成')
except Exception as e:
    print(f'初始化数据时出错: {str(e)}')
    sys.exit(1)
"
        
        if [ $? -ne 0 ]; then
            echo -e "${RED}初始化数据失败${NC}"
            exit 1
        else
            echo -e "${GREEN}基础数据初始化成功${NC}"
        fi
    else
        echo -e "${RED}找不到初始化脚本: scripts/init_all.py${NC}"
        exit 1
    fi
elif [ $DATA_STATUS -eq 2 ]; then
    echo -e "${RED}数据库缺少必要的表，请检查模型定义或迁移${NC}"
    exit 1
elif [ $DATA_STATUS -eq 3 ]; then
    echo -e "${RED}数据验证过程中出现错误${NC}"
    exit 1
else
    # 加载数据状态信息
    if [ -f ".data_status.json" ]; then
        SOURCES_COUNT=$(python -c "import json; f=open('.data_status.json'); data=json.load(f); print(data['sources_count']); f.close()")
        CATEGORIES_COUNT=$(python -c "import json; f=open('.data_status.json'); data=json.load(f); print(data['categories_count']); f.close()")
        TAGS_COUNT=$(python -c "import json; f=open('.data_status.json'); data=json.load(f); print(data['tags_count']); f.close()")
        echo -e "${GREEN}数据验证通过: sources: ${SOURCES_COUNT}, categories: ${CATEGORIES_COUNT}, tags: ${TAGS_COUNT}${NC}"
    else
        echo -e "${GREEN}数据验证通过${NC}"
    fi
fi

# 清理临时文件
rm -f .db_connection.json .migration_status.txt .data_status.json

# 回到项目根目录
cd ..

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
echo -e "停止环境: ${YELLOW}docker compose -f docker-compose.local.yml down${NC}"
echo -e "重置数据: ${YELLOW}docker compose -f docker-compose.local.yml down -v${NC}"
echo -e "${GREEN}=======================================${NC}" 