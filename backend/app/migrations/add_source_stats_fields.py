"""add news_count and last_response_time to source_stats

Revision ID: add_source_stats_fields
Revises: add_source_stats
Create Date: 2024-06-11 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_source_stats_fields'
down_revision = 'add_source_stats'  # 替换为实际的上一版本ID
branch_labels = None
depends_on = None

def upgrade():
    """升级数据库"""
    # 在 source_stats 表中添加 news_count 和 last_response_time 字段
    op.add_column('source_stats', sa.Column('news_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('source_stats', sa.Column('last_response_time', sa.Float(), nullable=False, server_default='0.0'))


def downgrade():
    """回滚数据库"""
    # 删除添加的字段
    op.drop_column('source_stats', 'news_count')
    op.drop_column('source_stats', 'last_response_time') 