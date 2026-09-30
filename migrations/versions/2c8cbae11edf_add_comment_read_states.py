"""add comment read states

Revision ID: 2c8cbae11edf
Revises: c463cd3fa41c
Create Date: 2026-10-01 00:05:49.286114
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = '2c8cbae11edf'
down_revision = 'c463cd3fa41c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('comment_read_states',
    sa.Column('question_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('last_read_comment_id', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('question_id', 'user_id')
    )
    with op.batch_alter_table('comment_read_states', schema=None) as batch_op:
        batch_op.create_index('ix_readstate_user_question', ['user_id', 'question_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('comment_read_states', schema=None) as batch_op:
        batch_op.drop_index('ix_readstate_user_question')

    op.drop_table('comment_read_states')
