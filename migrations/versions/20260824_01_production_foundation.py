"""Production foundation baseline.

Revision ID: 20260824_01
Revises:
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op

from hr_agent.database import Base
from hr_agent import models  # noqa: F401


revision: str = "20260824_01"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
