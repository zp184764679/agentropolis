"""Add housekeeping runtime state to game_state.

Revision ID: 0009_housekeeping_runtime_state
Revises: 0008_integerize_credit_fields
Create Date: 2026-03-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0009_housekeeping_runtime_state"
down_revision: str | None = "0008_integerize_credit_fields"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if _has_table("game_state") and not _has_column("game_state", "last_housekeeping_at"):
        op.add_column(
            "game_state",
            sa.Column("last_housekeeping_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    """Downgrade is intentionally a no-op for compatibility revisions."""

