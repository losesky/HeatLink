"""add news_count to sources

Revision ID: add_news_count_to_sources
Revises: add_news_count_cols
Create Date: 2024-03-19 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_news_count_to_sources'
down_revision = 'add_news_count_cols'
branch_labels = None
depends_on = None


def upgrade():
    # Check if news_count column already exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    columns = [c['name'] for c in inspector.get_columns('sources')]
    if 'news_count' not in columns:
        print("Adding news_count column to sources table...")
        op.add_column('sources', sa.Column('news_count', sa.Integer(), nullable=False, server_default='0'))
        print("news_count column added successfully")
    else:
        print("news_count column already exists in sources table, skipping")


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    columns = [c['name'] for c in inspector.get_columns('sources')]
    if 'news_count' in columns:
        print("Removing news_count column from sources table...")
        op.drop_column('sources', 'news_count')
        print("news_count column removed successfully")
    else:
        print("news_count column does not exist in sources table, skipping") 