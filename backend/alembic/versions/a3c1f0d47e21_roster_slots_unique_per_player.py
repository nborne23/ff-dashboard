"""roster_slots uniqueness per (team, week, player) instead of (team, week, slot)

The internal `Slot` vocabulary has a single `BN`/`IR` label and real rosters carry
several bench players per week, so `(team_id, week, slot)` can legitimately repeat.
A player, however, appears at most once per team-week.

Revision ID: a3c1f0d47e21
Revises: 4bdec88e6496
Create Date: 2026-07-12

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3c1f0d47e21"
down_revision: Union[str, None] = "4bdec88e6496"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite can't alter constraints in place; batch mode recreates the table.
    with op.batch_alter_table("roster_slots") as batch_op:
        batch_op.drop_constraint("uq_roster_slots_team_week_slot", type_="unique")
        batch_op.create_unique_constraint(
            "uq_roster_slots_team_week_player", ["team_id", "week", "player_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("roster_slots") as batch_op:
        batch_op.drop_constraint("uq_roster_slots_team_week_player", type_="unique")
        batch_op.create_unique_constraint(
            "uq_roster_slots_team_week_slot", ["team_id", "week", "slot"]
        )
