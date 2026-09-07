"""Create system_runtime table.

Revision ID: 0001
Revises: None
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_runtime",
        sa.Column("system_id", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("system_id"),
    )


def downgrade() -> None:
    op.drop_table("system_runtime")
