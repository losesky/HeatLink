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

# 启动数据库和缓存服务
echo -e "${YELLOW}正在启动数据库和缓存服务...${NC}"
docker compose -f docker-compose.local.yml up -d

# 等待服务启动
echo -e "${YELLOW}等待服务启动...${NC}"
sleep 5

# 运行数据库初始化和迁移
echo -e "${YELLOW}运行数据库初始化和迁移...${NC}"
cd backend

# 检查数据库
echo -e "${YELLOW}检查数据库连接...${NC}"
python -c "
import psycopg2
import time
import os
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
max_retries = 5
retry_delay = 2
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

# 检查是否有迁移文件
if [ -z "$(ls -A alembic/versions/)" ]; then
    echo -e "${YELLOW}创建初始迁移文件...${NC}"
    alembic revision --autogenerate -m "Initial migration"
fi

echo -e "${YELLOW}应用迁移...${NC}"
# 使用set +e允许命令失败不终止脚本
set +e
alembic upgrade head
MIGRATION_STATUS=$?

if [ $MIGRATION_STATUS -ne 0 ]; then
    echo -e "${RED}数据库迁移过程中出现错误${NC}"
    echo -e "${YELLOW}尝试创建初始数据库结构...${NC}"
    
    # 创建数据库中的表结构
    python -c "
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import time

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath('.'))

# 加载环境变量
load_dotenv()

# 从models导入所有模型以确保它们被注册
from app.db.session import Base
from app.models import *

# 获取数据库连接
from app.core.config import settings
engine = create_engine(settings.DATABASE_URL)

# 创建所有表
try:
    Base.metadata.create_all(engine)
    print('成功创建所有数据库表!')
except Exception as e:
    print(f'创建表时出错: {str(e)}')
    sys.exit(1)
"
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}无法创建数据库表结构${NC}"
    else
        echo -e "${GREEN}成功创建数据库表结构${NC}"
        # 再次尝试应用迁移
        echo -e "${YELLOW}重新应用迁移...${NC}"
        alembic stamp head
    fi
else
    echo -e "${GREEN}数据库迁移成功完成${NC}"
fi

# 检查是否需要初始化基础数据
echo -e "${YELLOW}检查是否需要初始化基础数据...${NC}"
python -c "
import os
import sys
import sqlalchemy
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath('.'))

# 加载环境变量
load_dotenv()

# 获取数据库连接
from app.core.config import settings
engine = create_engine(settings.DATABASE_URL)

# 检查sources表是否为空
try:
    with engine.connect() as conn:
        result = conn.execute(text('SELECT COUNT(*) FROM sources'))
        count = result.scalar()
        
    if count == 0:
        print('sources表为空，需要初始化数据')
        sys.exit(1)
    else:
        print(f'sources表已包含{count}条记录，无需初始化')
        sys.exit(0)
except Exception as e:
    print(f'检查数据时出错: {str(e)}')
    sys.exit(1)
"

INIT_NEEDED=$?
if [ $INIT_NEEDED -eq 1 ]; then
    echo -e "${YELLOW}初始化基础数据...${NC}"
    # 执行初始化脚本
    python scripts/init_all.py
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}初始化数据失败${NC}"
    else
        echo -e "${GREEN}基础数据初始化成功${NC}"
    fi
fi

# 恢复默认行为
set -e

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
echo -e "${GREEN}=======================================${NC}" 