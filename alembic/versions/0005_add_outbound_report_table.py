"""add outbound_report table

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-25 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "outbound_report",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("diagnostic_report_id", sa.String(length=36), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbound_report_incident_id", "outbound_report", ["incident_id"])
    op.create_index("ix_outbound_report_diagnostic_report_id", "outbound_report", ["diagnostic_report_id"])
    op.create_index("ix_outbound_report_status", "outbound_report", ["status"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_outbound_report_status")
    op.drop_index("ix_outbound_report_diagnostic_report_id")
    op.drop_index("ix_outbound_report_incident_id")
    op.drop_table("outbound_report")
