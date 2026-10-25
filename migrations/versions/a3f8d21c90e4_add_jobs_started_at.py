"""add jobs.started_at

任务超时回收（reap_stuck_jobs）原以 created_at 判超时——长排队任务会被
误标 failed。started_at 由 Worker 领取时写入，回收按 COALESCE(started_at,
created_at) 判定，旧行为对历史行保持兼容。

Revision ID: a3f8d21c90e4
Revises: 7d1e5c49ab02
Create Date: 2026-10-25 19:30:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = 'a3f8d21c90e4'
down_revision = '7d1e5c49ab02'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('started_at', sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_column('started_at')
