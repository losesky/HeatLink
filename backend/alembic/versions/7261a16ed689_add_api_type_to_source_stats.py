"""add_api_type_to_source_stats

Revision ID: 7261a16ed689
Revises: dffef90e48fa
Create Date: 2025-03-23 11:54:46.090492

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7261a16ed689'
down_revision = 'dffef90e48fa'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # 检查表是否存在
    if 'source_stats' not in inspector.get_table_names():
        print("source_stats表不存在，无法添加api_type字段")
        return
    
    # 检查列是否已存在
    columns = [c['name'] for c in inspector.get_columns('source_stats')]
    if 'api_type' in columns:
        print("api_type列已存在，无需添加")
        return
    
    try:
        # 检查枚举类型是否已存在
        with conn.begin():
            try:
                # 尝试查询现有的枚举类型
                conn.execute("SELECT pg_type.typname FROM pg_type JOIN pg_enum ON pg_enum.enumtypid = pg_type.oid WHERE pg_type.typname = 'apicalltype'")
                enum_exists = conn.fetchone() is not None
            except:
                enum_exists = False
        
        if not enum_exists:
            print("创建枚举类型apicalltype...")
            api_call_type = sa.Enum('internal', 'external', name='apicalltype')
            api_call_type.create(conn)
            print("枚举类型创建成功")
        else:
            print("枚举类型apicalltype已存在")
        
        # 添加api_type字段
        print("添加api_type字段...")
        op.add_column('source_stats', sa.Column('api_type', sa.Enum('internal', 'external', name='apicalltype'), 
                                               nullable=False, server_default='internal'))
        print("api_type字段添加成功")
    except Exception as e:
        print(f"迁移出错: {str(e)}")
        print("跳过添加api_type字段")


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # 检查表是否存在
    if 'source_stats' not in inspector.get_table_names():
        print("source_stats表不存在，无法删除api_type字段")
        return
    
    # 检查列是否存在
    columns = [c['name'] for c in inspector.get_columns('source_stats')]
    if 'api_type' not in columns:
        print("api_type列不存在，无需删除")
        return
    
    try:
        # 删除api_type字段
        print("删除api_type字段...")
        op.drop_column('source_stats', 'api_type')
        print("api_type字段删除成功")
        
        # 尝试删除枚举类型
        print("删除枚举类型apicalltype...")
        sa.Enum(name='apicalltype').drop(op.get_bind(), checkfirst=True)
        print("枚举类型删除成功")
    except Exception as e:
        print(f"回滚出错: {str(e)}")
        print("跳过删除api_type字段") 