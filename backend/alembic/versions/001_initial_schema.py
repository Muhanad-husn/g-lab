"""Initial schema — sessions, findings, action_log.

Revision ID: 001
Revises:
Create Date: 2026-03-04
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("preset_id", sa.Text(), nullable=True),
        sa.Column("canvas_state", sa.Text(), nullable=False),
        sa.Column("config", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default="active"
        ),
    )

    op.create_table(
        "findings",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Text(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("snapshot_png", sa.LargeBinary(), nullable=True),
        sa.Column("canvas_context", sa.Text(), nullable=True),
    )

    op.create_table(
        "action_log",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Text(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("guardrail_warnings", sa.Text(), nullable=True),
    )

    op.create_index(
        "idx_action_log_session",
        "action_log",
        ["session_id", "timestamp"],
    )


def downgrade() -> None:
    op.drop_index("idx_action_log_session", table_name="action_log")
    op.drop_table("action_log")
    op.drop_table("findings")
    op.drop_table("sessions")
