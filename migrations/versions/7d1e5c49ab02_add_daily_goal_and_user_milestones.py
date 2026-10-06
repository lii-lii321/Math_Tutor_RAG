"""add daily_goal and user_milestones

Revision ID: 7d1e5c49ab02
Revises: 2c8cbae11edf
Create Date: 2026-10-06 10:30:00.000000

users.daily_goal 可空（None → 回退 get_settings().daily_goal 全局默认，
保留 env 语义）；user_milestones 记录里程碑达成，(user_id, code) 唯一
保证每枚里程碑每用户至多一条。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = '7d1e5c49ab02'
down_revision = '2c8cbae11edf'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('daily_goal', sa.Integer(), nullable=True))

    op.create_table(
        'user_milestones',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('achieved_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'code', name='uq_user_milestone'),
    )
    with op.batch_alter_table('user_milestones', schema=None) as batch_op:
        batch_op.create_index('ix_user_milestones_user_id', ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('user_milestones', schema=None) as batch_op:
        batch_op.drop_index('ix_user_milestones_user_id')
    op.drop_table('user_milestones')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('daily_goal')
