"""add_idx_tickets_queued_recovery

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-11 12:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создает частичный индекс idx_tickets_queued_recovery для быстрого восстановления очередей."""
    op.create_index(
        "idx_tickets_queued_recovery",
        "tickets",
        ["line_id", "priority", "created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'queued'"),
    )


def downgrade() -> None:
    """Удаляет частичный индекс idx_tickets_queued_recovery."""
    op.drop_index(
        "idx_tickets_queued_recovery",
        table_name="tickets",
        postgresql_where=sa.text("status = 'queued'"),
    )
