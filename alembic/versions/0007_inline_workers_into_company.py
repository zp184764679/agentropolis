"""Inline legacy worker rows into company npc workforce fields.

Revision ID: 0007_inline_workers_into_company
Revises: 0006_order_time_in_force
Create Date: 2026-03-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0007_inline_workers_into_company"
down_revision: str | None = "0006_order_time_in_force"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_table("companies"):
        return

    if not _has_column("companies", "npc_worker_count"):
        op.add_column(
            "companies",
            sa.Column(
                "npc_worker_count",
                sa.Integer(),
                nullable=False,
                server_default="100",
            ),
        )
    if not _has_column("companies", "npc_satisfaction"):
        op.add_column(
            "companies",
            sa.Column(
                "npc_satisfaction",
                sa.Float(),
                nullable=False,
                server_default="100.0",
            ),
        )
    if not _has_column("companies", "last_consumption_at"):
        op.add_column(
            "companies",
            sa.Column("last_consumption_at", sa.DateTime(timezone=True), nullable=True),
        )

    if _has_table("workers"):
        op.execute(
            sa.text(
                """
                UPDATE companies
                SET npc_worker_count = COALESCE(
                        (SELECT workers.count FROM workers WHERE workers.company_id = companies.id),
                        npc_worker_count
                    ),
                    npc_satisfaction = COALESCE(
                        (SELECT workers.satisfaction FROM workers WHERE workers.company_id = companies.id),
                        npc_satisfaction
                    )
                """
            )
        )
        op.drop_table("workers")


def downgrade() -> None:
    """Downgrade is intentionally a no-op for compatibility revisions."""

