"""Add presets and conversation_messages tables (Phase 2).

Revision ID: 002
Revises: 001
Create Date: 2026-03-04
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "presets",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "is_system", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("config", sa.Text(), nullable=False),
    )

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Text(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("metadata", sa.Text(), nullable=True),
    )

    op.create_index(
        "idx_conversation_session_ts",
        "conversation_messages",
        ["session_id", "timestamp"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_conversation_session_ts",
        table_name="conversation_messages",
    )
    op.drop_table("conversation_messages")
    op.drop_table("presets")
