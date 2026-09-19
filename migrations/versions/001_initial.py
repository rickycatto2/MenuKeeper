"""Structured household cookbook, source records, history and conversions."""
from alembic import op
import sqlalchemy as sa
revision = '001'
down_revision = None
def upgrade():
    op.create_table('recipes', sa.Column('id', sa.String(), primary_key=True), sa.Column('household_id', sa.String(), nullable=False), sa.Column('body', sa.JSON(), nullable=False), sa.Column('search_text', sa.Text(), nullable=False), sa.Column('source', sa.JSON(), nullable=False), sa.Column('created_at', sa.String(), nullable=False), sa.Column('updated_at', sa.String(), nullable=False), sa.Column('deleted_at', sa.String(), nullable=True))
    op.create_index('ix_recipes_household_id', 'recipes', ['household_id'])
    op.create_table('history', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('recipe_id', sa.String(), nullable=False), sa.Column('date', sa.String(), nullable=False), sa.Column('note', sa.Text(), nullable=False), sa.Column('rating', sa.Integer(), nullable=True))
    op.create_index('ix_history_recipe_id', 'history', ['recipe_id'])
    op.create_table('conversions', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('body', sa.JSON(), nullable=False))
    table = sa.table('conversions', sa.column('body', sa.JSON()))
    op.bulk_insert(table, [{'body': x} for x in [
        {'name': 'all-purpose flour', 'aliases': ['flour', 'AP flour', 'plain flour'], 'grams_per_cup': 125, 'liquid': False},
        {'name': 'granulated sugar', 'aliases': ['sugar', 'white sugar'], 'grams_per_cup': 200, 'liquid': False},
        *[{'name': x, 'aliases': [], 'grams_per_cup': None, 'liquid': True} for x in ['water', 'milk', 'olive oil', 'lemon juice', 'balsamic vinegar', 'red wine vinegar', 'rice vinegar']]
    ]])
def downgrade():
    op.drop_table('history')
    op.drop_table('recipes')
    op.drop_table('conversions')
