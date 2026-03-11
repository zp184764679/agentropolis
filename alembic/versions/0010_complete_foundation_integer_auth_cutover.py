"""Complete foundation integer contracts and retire company API-key auth.

Revision ID: 0010_complete_foundation_integer_auth_cutover
Revises: 0009_housekeeping_runtime_state
Create Date: 2026-03-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0010_complete_foundation_integer_auth_cutover"
down_revision: str | None = "0009_housekeeping_runtime_state"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in _inspector().get_columns(table_name)}


def _round_integer_column(table_name: str, column_name: str) -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    bind.execute(sa.text(f"UPDATE {table_name} SET {column_name} = ROUND({column_name})"))
    if dialect == "postgresql":
        op.execute(
            sa.text(
                f"ALTER TABLE {table_name} "
                f"ALTER COLUMN {column_name} TYPE BIGINT "
                f"USING ROUND({column_name})::bigint"
            )
        )
    else:
        with op.batch_alter_table(table_name) as batch:
            batch.alter_column(
                column_name,
                existing_type=sa.Numeric(),
                type_=sa.BigInteger(),
                existing_nullable=False,
            )


def upgrade() -> None:
    if _has_table("inventories"):
        if _has_column("inventories", "quantity"):
            _round_integer_column("inventories", "quantity")
        if _has_column("inventories", "reserved"):
            _round_integer_column("inventories", "reserved")

    if _has_table("orders"):
        for column in ("price", "quantity", "remaining"):
            if _has_column("orders", column):
                _round_integer_column("orders", column)

    if _has_table("trades"):
        for column in ("price", "quantity"):
            if _has_column("trades", column):
                _round_integer_column("trades", column)

    if _has_table("price_history"):
        for column in ("open", "high", "low", "close", "volume"):
            if _has_column("price_history", column):
                _round_integer_column("price_history", column)

    if _has_table("companies") and _has_column("companies", "api_key_hash"):
        with op.batch_alter_table("companies") as batch:
            batch.drop_column("api_key_hash")


def downgrade() -> None:
    """Downgrade is intentionally a no-op for compatibility revisions."""

