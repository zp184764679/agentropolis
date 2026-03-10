"""Execution job model compatibility migration.

Revision ID: 0004_execution_job_model
Revises: 0003_preview_abuse_budget_guard
Create Date: 2026-03-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_execution_job_model"
down_revision: str | None = "0003_preview_abuse_budget_guard"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def upgrade() -> None:
    if not _has_table("execution_jobs"):
        op.create_table(
            "execution_jobs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("job_type", sa.String(length=48), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("trigger_kind", sa.String(length=24), nullable=False),
            sa.Column("dedupe_key", sa.String(length=160), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("result_summary", sa.JSON(), nullable=True),
            sa.Column("attempt_history", sa.JSON(), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("max_attempts", sa.Integer(), nullable=False),
            sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("dead_letter_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index("execution_jobs", "ix_execution_jobs_job_type"):
        op.create_index("ix_execution_jobs_job_type", "execution_jobs", ["job_type"])
    if not _has_index("execution_jobs", "ix_execution_jobs_status"):
        op.create_index("ix_execution_jobs_status", "execution_jobs", ["status"])
    if not _has_index("execution_jobs", "ix_execution_jobs_dedupe_key"):
        op.create_index("ix_execution_jobs_dedupe_key", "execution_jobs", ["dedupe_key"])
    if not _has_index("execution_jobs", "ix_execution_jobs_available_at"):
        op.create_index("ix_execution_jobs_available_at", "execution_jobs", ["available_at"])

    if _has_table("housekeeping_logs"):
        _add_column_if_missing(
            "housekeeping_logs",
            sa.Column("trigger_kind", sa.String(length=24), nullable=False, server_default="scheduled"),
        )
        _add_column_if_missing(
            "housekeeping_logs",
            sa.Column("execution_job_id", sa.Integer(), nullable=True),
        )
        _add_column_if_missing(
            "housekeeping_logs",
            sa.Column("phase_results", sa.JSON(), nullable=True),
        )
        if not _has_index("housekeeping_logs", "ix_housekeeping_logs_execution_job_id"):
            op.create_index(
                "ix_housekeeping_logs_execution_job_id",
                "housekeeping_logs",
                ["execution_job_id"],
            )


def downgrade() -> None:
    """Downgrade is intentionally a no-op for compatibility revisions."""

