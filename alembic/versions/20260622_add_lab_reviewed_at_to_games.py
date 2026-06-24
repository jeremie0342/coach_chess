"""add lab_reviewed_at to games

Revision ID: 7b2f1c8a4d9e
Revises: cabca61f3d33
Create Date: 2026-06-22 14:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7b2f1c8a4d9e'
down_revision: Union[str, None] = 'd03a678319ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('games', sa.Column('lab_reviewed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('games', 'lab_reviewed_at')
