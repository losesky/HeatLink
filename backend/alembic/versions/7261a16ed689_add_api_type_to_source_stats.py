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
    # 创建枚举类型
    api_call_type = sa.Enum('internal', 'external', name='apicalltype')
    api_call_type.create(op.get_bind())
    
    # 添加api_type字段
    op.add_column('source_stats', sa.Column('api_type', sa.Enum('internal', 'external', name='apicalltype'), 
                                            nullable=False, server_default='internal'))


def downgrade():
    # 删除api_type字段
    op.drop_column('source_stats', 'api_type')
    
    # 删除枚举类型
    sa.Enum(name='apicalltype').drop(op.get_bind()) 