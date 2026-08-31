"""team_logos cache, plus the logo source fields on teams

`team_logos` caches the bytes; `teams.logo_source_url` / `teams.logo_type` record what
the platform most recently said, and the two are compared to decide when the cache is
stale. An uploaded logo's URL carries a generated id that changes when the image
changes, so the comparison detects a swap exactly rather than expiring on a guess.

Both columns are nullable rather than defaulted to "": "no logo" and "blank URL" must
not collapse into one state, because that comparison is what drives invalidation.

Revision ID: 380dfc2ab9bc
Revises: 414238d8f6d2
Create Date: 2026-08-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "380dfc2ab9bc"
down_revision: Union[str, None] = "414238d8f6d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_logos",
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("team_id", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("content_type", sa.String(length=64), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("platform", "team_id"),
    )
    op.add_column("teams", sa.Column("logo_source_url", sa.String(length=1024), nullable=True))
    op.add_column("teams", sa.Column("logo_type", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("teams", "logo_type")
    op.drop_column("teams", "logo_source_url")
    op.drop_table("team_logos")
