"""player_pool_entries.waiver_clears — the day a waiver-wire player becomes a free agent

Revision ID: b81e4c2f6a39
Revises: a7d3e91c4b20
Create Date: 2026-11-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b81e4c2f6a39"
down_revision: Union[str, None] = "a7d3e91c4b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("player_pool_entries", sa.Column("waiver_clears", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("player_pool_entries", "waiver_clears")
