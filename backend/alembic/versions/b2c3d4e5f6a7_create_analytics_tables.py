"""create_analytics_tables

Revision ID: b2c3d4e5f6a7
Revises: f078d2afd420
Create Date: 2026-09-10 18:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "f078d2afd420"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema to include analytics tables."""
    # 1. ticket_feedbacks
    op.create_table(
        "ticket_feedbacks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "score >= 1 AND score <= 5", name="chk_feedback_score"
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id"),
    )
    op.create_index("idx_feedbacks_score", "ticket_feedbacks", ["score"])

    # 2. ticket_audits
    op.create_table(
        "ticket_audits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("politeness_score", sa.SmallInteger(), nullable=False),
        sa.Column("completeness_score", sa.SmallInteger(), nullable=False),
        sa.Column("root_cause", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "is_system_issue",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "politeness_score BETWEEN 1 AND 5", name="chk_audit_politeness"
        ),
        sa.CheckConstraint(
            "completeness_score BETWEEN 1 AND 5", name="chk_audit_completeness"
        ),
        sa.CheckConstraint(
            "root_cause IN ('operator_error', 'system_issue', 'regulation_dissatisfaction', 'none')",
            name="chk_audit_root_cause",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id"),
    )
    op.create_index(
        "idx_audits_system_issue",
        "ticket_audits",
        ["is_system_issue"],
        postgresql_where=sa.text("is_system_issue = true"),
    )

    # 3. system_incidents
    op.create_table(
        "system_incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("incident_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="open",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'in_review', 'resolved')",
            name="chk_incident_status",
        ),
        sa.CheckConstraint(
            "incident_type IN ('portal_downtime', 'crypto_plugin', 'api_error')",
            name="chk_incident_type",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_incidents_status",
        "system_incidents",
        ["status"],
        postgresql_where=sa.text("status = 'open'"),
    )

    # 4. operator_metrics_daily
    op.create_table(
        "operator_metrics_daily",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column(
            "total_tickets_handled",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "avg_first_response_time_sec",
            sa.Numeric(precision=8, scale=2),
            nullable=True,
        ),
        sa.Column(
            "avg_handling_time_sec",
            sa.Numeric(precision=8, scale=2),
            nullable=True,
        ),
        sa.Column(
            "avg_client_csat",
            sa.Numeric(precision=3, scale=2),
            nullable=True,
        ),
        sa.Column(
            "avg_adjusted_csat",
            sa.Numeric(precision=3, scale=2),
            nullable=True,
        ),
        sa.Column(
            "avg_ai_quality_score",
            sa.Numeric(precision=3, scale=2),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operator_id", "metric_date", name="uq_operator_daily_metrics"
        ),
    )
    op.create_index(
        "idx_operator_metrics_date", "operator_metrics_daily", ["metric_date"]
    )


def downgrade() -> None:
    """Downgrade schema to drop analytics tables."""
    op.drop_index(
        "idx_operator_metrics_date", table_name="operator_metrics_daily"
    )
    op.drop_table("operator_metrics_daily")
    op.drop_index(
        "idx_incidents_status",
        table_name="system_incidents",
        postgresql_where=sa.text("status = 'open'"),
    )
    op.drop_table("system_incidents")
    op.drop_index(
        "idx_audits_system_issue",
        table_name="ticket_audits",
        postgresql_where=sa.text("is_system_issue = true"),
    )
    op.drop_table("ticket_audits")
    op.drop_index("idx_feedbacks_score", table_name="ticket_feedbacks")
    op.drop_table("ticket_feedbacks")
