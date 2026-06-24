"""add opening_progress table

Revision ID: c5d8a2f9b6e4
Revises: a9c4e7b1f3d8
Create Date: 2026-06-22 18:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5d8a2f9b6e4'
down_revision: Union[str, None] = 'a9c4e7b1f3d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'opening_progress',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('player_id', sa.Integer(), sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('opening_key', sa.String(64), nullable=False, index=True),
        sa.Column('base_name', sa.String(64), nullable=False),
        sa.Column('user_color', sa.String(8), nullable=False),
        # State
        sa.Column('status', sa.String(16), nullable=False, server_default='active'),  # active | mastered
        sa.Column('streak_days', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_perfect_date', sa.Date(), nullable=True),
        sa.Column('best_streak', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('perfect_runs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('mastered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('player_id', 'opening_key', name='uq_opening_progress_player_key'),
    )
    op.create_index(
        'ix_opening_progress_player_status',
        'opening_progress',
        ['player_id', 'user_color', 'status'],
    )


def downgrade() -> None:
    op.drop_index('ix_opening_progress_player_status', table_name='opening_progress')
    op.drop_table('opening_progress')
