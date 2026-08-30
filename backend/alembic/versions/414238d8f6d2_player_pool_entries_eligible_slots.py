"""player_pool_entries.eligible_slots

A follow-up to 01698feffebb rather than an edit to it, because that revision is
already pushed.

The waiver comparison picks which of the user's starters a candidate is actually
competing with, and that needs ESPN's per-league eligibility list — a superflex
league admits a QB to `OP`, a TE-premium one admits a TE to `REC_FLEX`. Deriving
eligibility from `position` at read time would get both wrong, so it is persisted.

JSON-encoded list of unnumbered slot names, following `board_players.flags`.

Revision ID: 414238d8f6d2
Revises: 01698feffebb
Create Date: 2026-08-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "414238d8f6d2"
down_revision: Union[str, None] = "01698feffebb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "player_pool_entries",
        sa.Column("eligible_slots", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("player_pool_entries", "eligible_slots")
