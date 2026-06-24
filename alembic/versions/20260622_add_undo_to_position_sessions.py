"""add undo fields to position_sessions

Revision ID: e1f3d8a9c7b2
Revises: c5d8a2f9b6e4
Create Date: 2026-06-22 20:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f3d8a9c7b2'
down_revision: Union[str, None] = 'c5d8a2f9b6e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('position_sessions', sa.Column('max_undos', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('position_sessions', sa.Column('undos_used', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('position_sessions', 'undos_used')
    op.drop_column('position_sessions', 'max_undos')
