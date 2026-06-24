"""add live_debrief_reports

Revision ID: b3d9e2c7f5a1
Revises: a8c1e9f5d6b3
Create Date: 2026-06-23 20:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'b3d9e2c7f5a1'
down_revision: Union[str, None] = 'a8c1e9f5d6b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'live_debrief_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('game_id', sa.Integer(), sa.ForeignKey('games.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', JSONB, nullable=False),
        sa.Column('summary', JSONB, nullable=True),
        sa.Column('title', sa.String(256), nullable=True),
    )
    op.create_index('ix_live_debrief_reports_game_id', 'live_debrief_reports', ['game_id'])
    op.create_index('ix_live_debrief_reports_created_at', 'live_debrief_reports', ['created_at'])
    op.create_index('ix_live_debrief_created_at', 'live_debrief_reports', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_live_debrief_created_at', table_name='live_debrief_reports')
    op.drop_index('ix_live_debrief_reports_created_at', table_name='live_debrief_reports')
    op.drop_index('ix_live_debrief_reports_game_id', table_name='live_debrief_reports')
    op.drop_table('live_debrief_reports')
