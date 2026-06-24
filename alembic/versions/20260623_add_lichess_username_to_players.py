"""add lichess_username to players

Revision ID: d5e9f8a3c1b7
Revises: c7e5b3a9f1d2
Create Date: 2026-06-23 23:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5e9f8a3c1b7'
down_revision: Union[str, None] = 'c7e5b3a9f1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('players', sa.Column('lichess_username', sa.String(64), nullable=True))
    op.create_index('ix_players_lichess_username', 'players', ['lichess_username'])


def downgrade() -> None:
    op.drop_index('ix_players_lichess_username', table_name='players')
    op.drop_column('players', 'lichess_username')
