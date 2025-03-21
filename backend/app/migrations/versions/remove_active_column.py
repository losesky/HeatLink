"""remove active column from sources

Revision ID: remove_active_column
Revises: add_news_count_to_sources
Create Date: 2024-05-30 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'remove_active_column'
down_revision = 'add_news_count_to_sources'  # 修正为最新的迁移版本
branch_labels = None
depends_on = None

def upgrade():
    # 1. 首先打印操作开始信息
    op.execute("SELECT 1")  # 用于打印连接成功信息
    print("开始执行迁移操作...")
    
    # 2. 确保所有数据一致性
    print("更新数据一致性: active=true的记录")
    op.execute("""
        UPDATE sources 
        SET status = 'ACTIVE'
        WHERE active = true AND status <> 'ACTIVE';
    """)
    
    print("更新数据一致性: active=false的记录")
    op.execute("""
        UPDATE sources 
        SET status = 'INACTIVE'
        WHERE active = false AND status = 'ACTIVE';
    """)
    
    # 3. 删除active字段
    print("正在删除active字段...")
    op.drop_column('sources', 'active')
    print("active字段删除成功")


def downgrade():
    # 1. 添加active字段
    print("正在还原：添加active字段")
    op.add_column('sources', sa.Column('active', sa.BOOLEAN(), nullable=False, server_default='false'))
    
    # 2. 根据status字段设置active的值
    print("正在还原：根据status设置active值")
    op.execute("""
        UPDATE sources 
        SET active = CASE
            WHEN status = 'ACTIVE' THEN true
            ELSE false
        END;
    """)
    print("迁移回滚完成") 