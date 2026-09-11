"""add_timestamps_to_operator_metrics_daily

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-11 11:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add created_at, updated_at and composite index to operator_metrics_daily."""
    op.add_column(
        "operator_metrics_daily",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
    )
    op.add_column(
        "operator_metrics_daily",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_metrics_operator_period",
        "operator_metrics_daily",
        ["operator_id", sa.text("metric_date DESC")],
    )


def downgrade() -> None:
    """Remove created_at, updated_at and composite index from operator_metrics_daily."""
    op.drop_index(
        "idx_metrics_operator_period",
        table_name="operator_metrics_daily",
    )
    op.drop_column("operator_metrics_daily", "updated_at")
    op.drop_column("operator_metrics_daily", "created_at")
