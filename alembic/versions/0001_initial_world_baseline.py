"""Initial world baseline.

Revision ID: 0001_initial_world_baseline
Revises:
Create Date: 2026-03-10
"""

from collections.abc import Sequence

from alembic import op

from agentropolis.models import Base

# revision identifiers, used by Alembic.
revision: str = "0001_initial_world_baseline"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
