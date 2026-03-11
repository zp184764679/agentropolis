"""Integerize scaffold credit fields that now use BigInteger models.

Revision ID: 0008_integerize_credit_fields
Revises: 0007_inline_workers_into_company
Create Date: 2026-03-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0008_integerize_credit_fields"
down_revision: str | None = "0007_inline_workers_into_company"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if _has_table("resources") and _has_column("resources", "base_price"):
        bind.execute(sa.text("UPDATE resources SET base_price = ROUND(base_price)"))
        if dialect == "postgresql":
            op.execute(
                sa.text(
                    "ALTER TABLE resources "
                    "ALTER COLUMN base_price TYPE BIGINT "
                    "USING ROUND(base_price)::bigint"
                )
            )

    if _has_table("building_types") and _has_column("building_types", "cost_credits"):
        bind.execute(sa.text("UPDATE building_types SET cost_credits = ROUND(cost_credits)"))
        if dialect == "postgresql":
            op.execute(
                sa.text(
                    "ALTER TABLE building_types "
                    "ALTER COLUMN cost_credits TYPE BIGINT "
                    "USING ROUND(cost_credits)::bigint"
                )
            )

    if _has_table("companies"):
        if _has_column("companies", "balance"):
            bind.execute(sa.text("UPDATE companies SET balance = ROUND(balance)"))
            if dialect == "postgresql":
                op.execute(
                    sa.text(
                        "ALTER TABLE companies "
                        "ALTER COLUMN balance TYPE BIGINT "
                        "USING ROUND(balance)::bigint"
                    )
                )
        if _has_column("companies", "net_worth"):
            bind.execute(sa.text("UPDATE companies SET net_worth = ROUND(net_worth)"))
            if dialect == "postgresql":
                op.execute(
                    sa.text(
                        "ALTER TABLE companies "
                        "ALTER COLUMN net_worth TYPE BIGINT "
                        "USING ROUND(net_worth)::bigint"
                    )
                )


def downgrade() -> None:
    """Downgrade is intentionally a no-op for compatibility revisions."""

