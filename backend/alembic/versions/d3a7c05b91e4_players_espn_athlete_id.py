"""players.espn_athlete_id — the cross-platform bridge to ESPN's injury API

Revision ID: d3a7c05b91e4
Revises: c9f2b6d4e871
Create Date: 2026-09-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3a7c05b91e4"
down_revision: Union[str, None] = "c9f2b6d4e871"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("players", sa.Column("espn_athlete_id", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "espn_athlete_id")
