"""P5 autonomy core compatibility migration.

Revision ID: 0002_p5_autonomy_core
Revises: 0001_initial_world_baseline
Create Date: 2026-03-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_p5_autonomy_core"
down_revision: str | None = "0001_initial_world_baseline"
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

    if _has_table("autonomy_states"):
        _add_column_if_missing(
            "autonomy_states",
            sa.Column("autopilot_enabled", sa.Boolean(), nullable=True),
        )
        _add_column_if_missing(
            "autonomy_states",
            sa.Column("standing_orders", sa.JSON(), nullable=True),
        )
        _add_column_if_missing(
            "autonomy_states",
            sa.Column("spending_limit_per_hour", sa.BigInteger(), nullable=True),
        )
        _add_column_if_missing(
            "autonomy_states",
            sa.Column("spending_this_hour", sa.BigInteger(), nullable=True),
        )
        _add_column_if_missing(
            "autonomy_states",
            sa.Column("hour_window_started_at", sa.DateTime(timezone=True), nullable=True),
        )
        _add_column_if_missing(
            "autonomy_states",
            sa.Column("last_reflex_at", sa.DateTime(timezone=True), nullable=True),
        )
        _add_column_if_missing(
            "autonomy_states",
            sa.Column("last_standing_orders_at", sa.DateTime(timezone=True), nullable=True),
        )
        _add_column_if_missing(
            "autonomy_states",
            sa.Column("last_digest_at", sa.DateTime(timezone=True), nullable=True),
        )
        _add_column_if_missing(
            "autonomy_states",
            sa.Column("reflex_log", sa.JSON(), nullable=True),
        )

        if _has_column("autonomy_states", "is_enabled"):
            bind.execute(
                sa.text(
                    """
                    UPDATE autonomy_states
                    SET autopilot_enabled = COALESCE(autopilot_enabled, is_enabled)
                    WHERE autopilot_enabled IS NULL
                    """
                )
            )

        bind.execute(
            sa.text(
                """
                UPDATE autonomy_states
                SET autopilot_enabled = COALESCE(autopilot_enabled, 0),
                    mode = COALESCE(mode, 'manual'),
                    standing_orders = COALESCE(standing_orders, '{}'),
                    spending_limit_per_hour = COALESCE(spending_limit_per_hour, 2500),
                    spending_this_hour = COALESCE(spending_this_hour, 0),
                    hour_window_started_at = COALESCE(hour_window_started_at, CURRENT_TIMESTAMP),
                    reflex_log = COALESCE(reflex_log, '[]'),
                    state = COALESCE(state, '{}')
                """
            )
        )

    if _has_table("agent_goals"):
        _add_column_if_missing(
            "agent_goals",
            sa.Column("status", sa.String(length=20), nullable=True),
        )
        _add_column_if_missing(
            "agent_goals",
            sa.Column("target", sa.JSON(), nullable=True),
        )
        _add_column_if_missing(
            "agent_goals",
            sa.Column("progress", sa.JSON(), nullable=True),
        )
        _add_column_if_missing(
            "agent_goals",
            sa.Column("notes", sa.Text(), nullable=True),
        )
        _add_column_if_missing(
            "agent_goals",
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )

        if _has_column("agent_goals", "payload"):
            bind.execute(
                sa.text(
                    """
                    UPDATE agent_goals
                    SET target = COALESCE(target, payload)
                    WHERE target IS NULL
                    """
                )
            )
        bind.execute(
            sa.text(
                """
                UPDATE agent_goals
                SET target = COALESCE(target, '{}'),
                    progress = COALESCE(progress, '{}')
                """
            )
        )
        if _has_column("agent_goals", "is_completed"):
            bind.execute(
                sa.text(
                    """
                    UPDATE agent_goals
                    SET status = CASE
                        WHEN status IS NOT NULL THEN status
                        WHEN is_completed = 1 THEN 'COMPLETED'
                        ELSE 'ACTIVE'
                    END,
                    completed_at = CASE
                        WHEN completed_at IS NOT NULL THEN completed_at
                        WHEN is_completed = 1 THEN CURRENT_TIMESTAMP
                        ELSE completed_at
                    END
                    """
                )
            )
        else:
            bind.execute(
                sa.text(
                    """
                    UPDATE agent_goals
                    SET status = COALESCE(status, 'ACTIVE')
                    """
                )
            )

    if _has_table("housekeeping_logs"):
        _add_column_if_missing(
            "housekeeping_logs",
            sa.Column("autonomy_summary", sa.JSON(), nullable=True),
        )
        _add_column_if_missing(
            "housekeeping_logs",
            sa.Column("digest_summary", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    """Downgrade is intentionally a no-op.

    Revision 0001 creates tables from current metadata, so strict column-level
    reversal is not reliable across mixed legacy/head states.
    """

