"""settings: leagues.is_enabled + app_settings table

Backs the Settings screen's ESPN Leagues card (task 7.3, per-league enable toggle) and
Preferences card (task 7.4, server-persisted live-refresh tier via a tiny key/value table).

Revision ID: 42de0534b16d
Revises: a3c1f0d47e21
Create Date: 2026-07-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "42de0534b16d"
down_revision: Union[str, None] = "a3c1f0d47e21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leagues",
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.String(255), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    # SQLite can't drop a column in place; batch mode recreates the table.
    with op.batch_alter_table("leagues") as batch_op:
        batch_op.drop_column("is_enabled")
