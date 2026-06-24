"""add player_repertoire_entries table

Revision ID: e7b1f4d9a2c6
Revises: d5e9f8a3c1b7
Create Date: 2026-06-24 12:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7b1f4d9a2c6'
down_revision: Union[str, None] = 'd5e9f8a3c1b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'player_repertoire_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('player_id', sa.Integer(), sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('opening_key', sa.String(64), nullable=False),
        sa.Column('base_name', sa.String(64), nullable=False),
        sa.Column('user_color', sa.String(8), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('player_id', 'opening_key', name='uq_player_repertoire_entry'),
    )
    op.create_index(
        'ix_player_repertoire_color',
        'player_repertoire_entries',
        ['player_id', 'user_color'],
    )


def downgrade() -> None:
    op.drop_index('ix_player_repertoire_color', table_name='player_repertoire_entries')
    op.drop_table('player_repertoire_entries')
