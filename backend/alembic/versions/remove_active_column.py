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
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    print("开始执行迁移操作...")
    
    # 检查sources表中是否存在status列
    columns = [c['name'] for c in inspector.get_columns('sources')]
    
    # 如果status列不存在，先添加它
    if 'status' not in columns:
        print("添加status列到sources表...")
        op.add_column('sources', sa.Column('status', sa.String(20), nullable=True))
        
        # 根据active字段设置status的初始值
        print("根据active字段初始化status值...")
        op.execute("""
            UPDATE sources 
            SET status = CASE
                WHEN active = true THEN 'ACTIVE'
                ELSE 'INACTIVE'
            END;
        """)
        print("status列添加并初始化完成")
    
    # 检查active列是否存在
    if 'active' in columns:
        # 如果status和active都存在，确保数据一致性
        print("确保active和status字段数据一致性...")
        
        # 尝试更新，但用try/except捕获可能的错误
        try:
            op.execute("""
                UPDATE sources 
                SET status = 'ACTIVE'
                WHERE active = true AND (status <> 'ACTIVE' OR status IS NULL);
            """)
            
            op.execute("""
                UPDATE sources 
                SET status = 'INACTIVE'
                WHERE active = false AND (status = 'ACTIVE' OR status IS NULL);
            """)
            print("数据一致性更新完成")
            
            # 删除active字段
            print("正在删除active字段...")
            op.drop_column('sources', 'active')
            print("active字段删除成功")
        except Exception as e:
            print(f"迁移出错: {str(e)}")
            print("跳过数据更新和列删除操作")
    else:
        print("active列不存在，无需删除")


def downgrade():
    # 检查active列是否已存在
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('sources')]
    
    if 'active' not in columns:
        print("正在还原：添加active字段")
        op.add_column('sources', sa.Column('active', sa.BOOLEAN(), nullable=False, server_default='false'))
        
        # 检查status列是否存在
        if 'status' in columns:
            print("正在还原：根据status设置active值")
            try:
                op.execute("""
                    UPDATE sources 
                    SET active = CASE
                        WHEN status = 'ACTIVE' THEN true
                        ELSE false
                    END;
                """)
                print("active字段值设置完成")
            except Exception as e:
                print(f"设置active值出错: {str(e)}")
    else:
        print("active列已存在，无需还原") 