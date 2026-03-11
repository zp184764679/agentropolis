"""Maintenance compatibility migration for notifications and perishable decay.

Revision ID: 0005_design_gap_maintenance
Revises: 0004_execution_job_model
Create Date: 2026-03-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005_design_gap_maintenance"
down_revision: str | None = "0004_execution_job_model"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def upgrade() -> None:
    if _has_table("inventories"):
        _add_column_if_missing(
            "inventories",
            sa.Column("last_decay_at", sa.DateTime(timezone=True), nullable=True),
        )

    if _has_table("resources"):
        _add_column_if_missing(
            "resources",
            sa.Column("is_perishable", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        _add_column_if_missing(
            "resources",
            sa.Column("decay_rate_per_hour", sa.Float(), nullable=False, server_default="0"),
        )

        bind = op.get_bind()
        bind.execute(
            sa.text(
                """
                UPDATE resources
                SET is_perishable = CASE WHEN ticker IN ('RAT', 'DW') THEN 1 ELSE 0 END,
                    decay_rate_per_hour = CASE WHEN ticker IN ('RAT', 'DW') THEN 0.05 ELSE 0 END
                """
            )
        )


def downgrade() -> None:
    """Downgrade is intentionally a no-op for compatibility revisions."""

