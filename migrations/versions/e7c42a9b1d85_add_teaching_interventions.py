"""add teaching_interventions + questions.retest_verified_at

教学闭环 MVP：一次教学干预（诊断→练习→独立作答→延迟复测）的全生命周期
记录表；questions.retest_verified_at 为延迟复测确认时间——mastered 归档
门槛从「SM-2 达标」升级为「SM-2 达标 + 复测通过」。

向后兼容：对已满足 reps>=3 且 interval_days>=21 的存量题回填
retest_verified_at=当前时刻——已掌握的题保持掌握，新题走复测闭环。

Revision ID: e7c42a9b1d85
Revises: a3f8d21c90e4
Create Date: 2026-10-25 20:05:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = 'e7c42a9b1d85'
down_revision = 'a3f8d21c90e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'teaching_interventions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('knowledge_point', sa.String(length=128), nullable=False),
        sa.Column('strategy', sa.String(length=32), nullable=False),
        sa.Column('question_ids', sa.JSON(), nullable=False),
        sa.Column('variant_source_id', sa.Integer(), nullable=True),
        sa.Column('outcome', sa.String(length=24), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('retest_due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('teaching_interventions', schema=None) as batch_op:
        batch_op.create_index('ix_teaching_user_kp', ['user_id', 'knowledge_point'], unique=False)
        batch_op.create_index(batch_op.f('ix_teaching_interventions_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('retest_verified_at', sa.DateTime(timezone=True), nullable=True)
        )

    # 存量已掌握题回填：保持既有 mastered 状态不被复测门槛破坏
    op.execute(
        "UPDATE questions SET retest_verified_at = CURRENT_TIMESTAMP "
        "WHERE reps >= 3 AND interval_days >= 21"
    )


def downgrade() -> None:
    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.drop_column('retest_verified_at')

    with op.batch_alter_table('teaching_interventions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_teaching_interventions_user_id'))
        batch_op.drop_index('ix_teaching_user_kp')

    op.drop_table('teaching_interventions')
