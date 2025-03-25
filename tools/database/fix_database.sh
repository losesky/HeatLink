#!/bin/bash

# 设置颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}   HeatLink 数据库修复脚本   ${NC}"
echo -e "${GREEN}=======================================${NC}"

echo -e "${YELLOW}正在检查数据库服务状态...${NC}"
docker compose -f docker-compose.local.yml ps postgres | grep "running" > /dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}PostgreSQL 服务未运行，尝试启动服务...${NC}"
    docker compose -f docker-compose.local.yml up -d postgres
    sleep 5
fi

# 直接设置环境变量
echo -e "${YELLOW}设置数据库连接环境变量...${NC}"
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/heatlink_dev"
export TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/heatlink_test_dev"
echo "已设置数据库连接环境变量为localhost"

echo -e "${YELLOW}初始化数据库表结构...${NC}"
cd backend

# 创建一个临时Python脚本，直接使用我们设置的环境变量
cat > temp_init_db.py << EOL
"""
初始化数据库表结构，无需依赖Alembic迁移
直接使用环境变量中的数据库连接
"""

import os
import sys
from sqlalchemy import create_engine
import time

# 直接获取环境变量中的数据库连接
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("错误: 未设置DATABASE_URL环境变量")
    sys.exit(1)

# 从models导入所有模型以确保它们被注册
from app.db.session import Base

# 先导入没有外键引用的模型
from app.models.category import Category
from app.models.tag import Tag

# 导入有关系的模型（顺序很重要）
from app.models.user import User, Subscription, user_favorite, user_read_history
from app.models.source_stats import SourceStats, ApiCallType
from app.models.source import Source, SourceAlias, SourceType, SourceStatus
from app.models.news import News, news_tag

def init_db():
    """
    初始化数据库表结构
    """
    print(f"连接到数据库: {DATABASE_URL}")
    
    try:
        engine = create_engine(DATABASE_URL)
        
        # 创建所有表
        print("开始创建数据库表...")
        Base.metadata.create_all(engine)
        print("成功创建所有表!")
        
        return True
    except Exception as e:
        print(f"创建表时出错: {str(e)}")
        return False

if __name__ == "__main__":
    if init_db():
        print("数据库初始化成功，现在您可以启动服务器了!")
    else:
        print("数据库初始化失败，请检查连接和权限设置")
        sys.exit(1)
EOL

# 运行临时脚本
python temp_init_db.py

if [ $? -ne 0 ]; then
    echo -e "${RED}数据库初始化失败${NC}"
    # 清理临时脚本
    rm -f temp_init_db.py
    cd ..
    exit 1
fi

# 清理临时脚本
rm -f temp_init_db.py

echo -e "${YELLOW}设置数据库迁移版本...${NC}"
# 使用环境变量运行alembic
PYTHONPATH=. alembic stamp head

if [ $? -ne 0 ]; then
    echo -e "${RED}设置迁移版本失败${NC}"
else
    echo -e "${GREEN}成功设置迁移版本为最新${NC}"
fi

echo -e "${YELLOW}检查数据库表是否需要初始化基础数据...${NC}"
python -c "
import os
import sys
from sqlalchemy import create_engine, text

# 直接获取环境变量中的数据库连接
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print('错误: 未设置DATABASE_URL环境变量')
    sys.exit(2)

# 创建数据库连接
engine = create_engine(DATABASE_URL)

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
    sys.exit(2)
"

INIT_NEEDED=$?
if [ $INIT_NEEDED -eq 1 ]; then
    echo -e "${YELLOW}初始化基础数据...${NC}"
    # 如果init_all.py存在，执行它
    if [ -f "scripts/init_all.py" ]; then
        # 使用环境变量执行初始化脚本
        python scripts/init_all.py
        
        if [ $? -ne 0 ]; then
            echo -e "${RED}初始化数据失败${NC}"
            cd ..
            exit 1
        else
            echo -e "${GREEN}基础数据初始化成功${NC}"
        fi
    else
        echo -e "${RED}找不到初始化脚本: scripts/init_all.py${NC}"
        cd ..
        exit 1
    fi
fi

cd ..

echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}数据库修复完成!${NC}"
echo -e "${GREEN}=======================================${NC}"
echo -e "现在您可以尝试启动服务器:"
echo -e "${YELLOW}cd backend && python start_server.py${NC}"
echo -e "${GREEN}=======================================${NC}" 