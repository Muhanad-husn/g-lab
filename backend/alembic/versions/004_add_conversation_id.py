"""Add conversation_id to conversation_messages for multi-conversation support.

Revision ID: 004
Revises: 003
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add conversation_id column — default to session_id for existing rows
    # so each session's existing messages form one "legacy" conversation.
    op.add_column(
        "conversation_messages",
        sa.Column(
            "conversation_id",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )

    # Backfill: set conversation_id = session_id for all existing rows
    op.execute(
        "UPDATE conversation_messages SET conversation_id = session_id WHERE conversation_id = ''"
    )

    # Drop the server default now that backfill is done
    # (SQLite doesn't support ALTER COLUMN, but new rows will always
    # have conversation_id set by the service layer)

    # Add index for efficient per-conversation queries
    op.create_index(
        "idx_conversation_conv_id_ts",
        "conversation_messages",
        ["conversation_id", "timestamp"],
    )

    # Add index for listing conversations per session
    op.create_index(
        "idx_conversation_session_conv",
        "conversation_messages",
        ["session_id", "conversation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_conversation_session_conv",
        table_name="conversation_messages",
    )
    op.drop_index(
        "idx_conversation_conv_id_ts",
        table_name="conversation_messages",
    )
    # SQLite doesn't support DROP COLUMN in older versions,
    # but modern SQLite (3.35+) does.
    op.drop_column("conversation_messages", "conversation_id")
