"""Add order time-in-force for IOC/GTC market semantics.

Revision ID: 0006_order_time_in_force
Revises: 0005_design_gap_maintenance
Create Date: 2026-03-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0006_order_time_in_force"
down_revision: str | None = "0005_design_gap_maintenance"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_table("orders") or _has_column("orders", "time_in_force"):
        return
    op.add_column(
        "orders",
        sa.Column(
            "time_in_force",
            sa.Enum("GTC", "IOC", name="timeinforce"),
            nullable=False,
            server_default="GTC",
        ),
    )


def downgrade() -> None:
    """Downgrade is intentionally a no-op for compatibility revisions."""

