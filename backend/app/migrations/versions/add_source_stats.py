"""add source stats

Revision ID: add_source_stats
Revises: previous_revision
Create Date: 2024-03-21 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = 'add_source_stats'
down_revision = 'previous_revision'  # 替换为实际的上一版本ID
branch_labels = None
depends_on = None

def upgrade():
    # 创建 SourceStatus 枚举类型
    op.execute("CREATE TYPE sourcestatus AS ENUM ('active', 'error', 'warning', 'inactive')")
    
    # 更新 Source 表
    op.add_column('sources', sa.Column('status', sa.Enum('active', 'error', 'warning', 'inactive', name='sourcestatus'), nullable=False, server_default='inactive'))
    op.add_column('sources', sa.Column('last_update', sa.DateTime(), nullable=True))
    
    # 创建 SourceStats 表
    op.create_table(
        'source_stats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('success_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('avg_response_time', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('total_requests', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_source_stats_id'), 'source_stats', ['id'], unique=False)
    op.create_index(op.f('ix_source_stats_source_id'), 'source_stats', ['source_id'], unique=False)

def downgrade():
    # 删除 SourceStats 表
    op.drop_index(op.f('ix_source_stats_source_id'), table_name='source_stats')
    op.drop_index(op.f('ix_source_stats_id'), table_name='source_stats')
    op.drop_table('source_stats')
    
    # 更新 Source 表
    op.drop_column('sources', 'last_update')
    op.drop_column('sources', 'status')
    
    # 删除 SourceStatus 枚举类型
    op.execute('DROP TYPE sourcestatus') 