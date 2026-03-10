"""Preview abuse/budget guard compatibility migration.

Revision ID: 0003_preview_abuse_budget_guard
Revises: 0002_p5_autonomy_core
Create Date: 2026-03-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_preview_abuse_budget_guard"
down_revision: str | None = "0002_p5_autonomy_core"
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
    bind = op.get_bind()

    if _has_table("preview_agent_policies"):
        _add_column_if_missing(
            "preview_agent_policies",
            sa.Column("operation_budgets", sa.JSON(), nullable=True),
        )
        _add_column_if_missing(
            "preview_agent_policies",
            sa.Column("denied_operations", sa.JSON(), nullable=True),
        )
        _add_column_if_missing(
            "preview_agent_policies",
            sa.Column("max_spend_per_operation", sa.BigInteger(), nullable=True),
        )
        _add_column_if_missing(
            "preview_agent_policies",
            sa.Column("remaining_spend_budget", sa.BigInteger(), nullable=True),
        )
        _add_column_if_missing(
            "preview_agent_policies",
            sa.Column("last_spending_refill_at", sa.DateTime(timezone=True), nullable=True),
        )

        bind.execute(
            sa.text(
                """
                UPDATE preview_agent_policies
                SET operation_budgets = COALESCE(operation_budgets, '{}')
                """
            )
        )


def downgrade() -> None:
    """Downgrade is intentionally a no-op for compatibility revisions."""

