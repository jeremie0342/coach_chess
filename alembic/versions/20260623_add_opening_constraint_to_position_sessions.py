"""add opening constraint to position_sessions

Revision ID: f4a8c2e7d1b9
Revises: e1f3d8a9c7b2
Create Date: 2026-06-23 10:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'f4a8c2e7d1b9'
down_revision: Union[str, None] = 'e1f3d8a9c7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('position_sessions', sa.Column('opening_key', sa.String(64), nullable=True))
    op.add_column('position_sessions', sa.Column('opening_branch_label', sa.String(128), nullable=True))
    op.add_column('position_sessions', sa.Column('opening_moves', JSONB, nullable=True))
    op.add_column('position_sessions', sa.Column('opening_ply_index', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('position_sessions', sa.Column('opening_status', sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column('position_sessions', 'opening_status')
    op.drop_column('position_sessions', 'opening_ply_index')
    op.drop_column('position_sessions', 'opening_moves')
    op.drop_column('position_sessions', 'opening_branch_label')
    op.drop_column('position_sessions', 'opening_key')
