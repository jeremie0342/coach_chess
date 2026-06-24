"""add scout_snapshots

Revision ID: a8c1e9f5d6b3
Revises: f4a8c2e7d1b9
Create Date: 2026-06-23 18:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'a8c1e9f5d6b3'
down_revision: Union[str, None] = 'f4a8c2e7d1b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'scout_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('opponent_username', sa.String(64), nullable=False),
        sa.Column('scouted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', JSONB, nullable=False),
        sa.Column('summary', JSONB, nullable=True),
    )
    op.create_index('ix_scout_snapshots_opponent_username', 'scout_snapshots', ['opponent_username'])
    op.create_index('ix_scout_snapshots_scouted_at', 'scout_snapshots', ['scouted_at'])
    op.create_index('ix_scout_snapshots_user_time', 'scout_snapshots', ['opponent_username', 'scouted_at'])


def downgrade() -> None:
    op.drop_index('ix_scout_snapshots_user_time', table_name='scout_snapshots')
    op.drop_index('ix_scout_snapshots_scouted_at', table_name='scout_snapshots')
    op.drop_index('ix_scout_snapshots_opponent_username', table_name='scout_snapshots')
    op.drop_table('scout_snapshots')
