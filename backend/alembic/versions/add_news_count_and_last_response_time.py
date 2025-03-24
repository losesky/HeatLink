"""add news_count and last_response_time to source_stats

Revision ID: add_news_count_cols
Revises: 75c36535602c
Create Date: 2024-03-19 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_news_count_cols'
down_revision = '75c36535602c'
branch_labels = None
depends_on = None


def upgrade():
    # Check if the source_stats table exists first
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    if 'source_stats' not in tables:
        # Create the source_stats table if it doesn't exist
        print("source_stats table does not exist, creating it...")
        op.create_table('source_stats',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('source_id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('success_rate', sa.Float(), nullable=True),
            sa.Column('avg_response_time', sa.Float(), nullable=True),
            sa.Column('total_requests', sa.Integer(), nullable=True),
            sa.Column('error_count', sa.Integer(), nullable=True),
            sa.Column('news_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('last_response_time', sa.Float(), nullable=False, server_default='0.0'),
            sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('idx_source_stats_source_id', 'source_stats', ['source_id'], unique=False)
        op.create_index('idx_source_stats_created_at', 'source_stats', ['created_at'], unique=False)
        print("source_stats table created successfully")
    else:
        # If the table exists, add the columns
        print("Adding columns to existing source_stats table...")
        # Check if the columns already exist
        columns = [c['name'] for c in inspector.get_columns('source_stats')]
        
        if 'news_count' not in columns:
            op.add_column('source_stats', sa.Column('news_count', sa.Integer(), nullable=False, server_default='0'))
        
        if 'last_response_time' not in columns:
            op.add_column('source_stats', sa.Column('last_response_time', sa.Float(), nullable=False, server_default='0.0'))
        print("Columns added successfully")


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'source_stats' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('source_stats')]
        
        if 'last_response_time' in columns:
            op.drop_column('source_stats', 'last_response_time')
            
        if 'news_count' in columns:
            op.drop_column('source_stats', 'news_count')
    # Don't drop the entire table during downgrade 