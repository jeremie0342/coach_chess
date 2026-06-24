"""add details JSONB to weekly_reports

Revision ID: c7e5b3a9f1d2
Revises: b3d9e2c7f5a1
Create Date: 2026-06-23 22:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'c7e5b3a9f1d2'
down_revision: Union[str, None] = 'b3d9e2c7f5a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('weekly_reports', sa.Column('details', JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column('weekly_reports', 'details')
