"""add last_solved_at to exercises

Revision ID: a9c4e7b1f3d8
Revises: 7b2f1c8a4d9e
Create Date: 2026-06-22 17:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a9c4e7b1f3d8'
down_revision: Union[str, None] = '7b2f1c8a4d9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('exercises', sa.Column('last_solved_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_exercises_last_solved_at', 'exercises', ['last_solved_at'])


def downgrade() -> None:
    op.drop_index('ix_exercises_last_solved_at', table_name='exercises')
    op.drop_column('exercises', 'last_solved_at')
