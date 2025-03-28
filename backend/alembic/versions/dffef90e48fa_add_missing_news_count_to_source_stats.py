"""add missing news_count to source_stats

Revision ID: dffef90e48fa
Revises: remove_active_column
Create Date: 2025-03-21 20:05:16.103704

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'dffef90e48fa'
down_revision = 'remove_active_column'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    # Remove problematic commands that change title column length 
    # or drop and recreate tables, just add the missing columns
    
    # Check if the source_stats table exists first
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    if 'source_stats' in tables:
        # Check if the columns already exist
        columns = [c['name'] for c in inspector.get_columns('source_stats')]
        
        # Add the missing news_count column if it doesn't exist
        if 'news_count' not in columns:
            print("Adding news_count column to source_stats table...")
            op.add_column('source_stats', sa.Column('news_count', sa.Integer(), 
                                                   nullable=False, server_default='0'))
            print("news_count column added successfully")
            
        # Add the missing last_response_time column if it doesn't exist
        if 'last_response_time' not in columns:
            print("Adding last_response_time column to source_stats table...")
            op.add_column('source_stats', sa.Column('last_response_time', sa.Float(), 
                                                   nullable=False, server_default='0.0'))
            print("last_response_time column added successfully")
    else:
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
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    # Also simplify the downgrade to just remove the columns we're adding
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'source_stats' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('source_stats')]
        
        if 'last_response_time' in columns:
            op.drop_column('source_stats', 'last_response_time')
            
        if 'news_count' in columns:
            op.drop_column('source_stats', 'news_count')
    # ### end Alembic commands ### 