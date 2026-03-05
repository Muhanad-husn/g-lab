"""Add document_libraries, documents, session_library_attachments tables (Phase 3).

Revision ID: 003
Revises: 002
Create Date: 2026-03-05
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_libraries",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("doc_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parse_quality", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.Text(), nullable=True),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "library_id",
            sa.Text(),
            sa.ForeignKey("document_libraries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("file_hash", sa.Text(), nullable=False),
        sa.Column("parse_tier", sa.Text(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_at", sa.Text(), nullable=False),
    )

    op.create_index(
        "idx_documents_library_id",
        "documents",
        ["library_id"],
    )

    op.create_table(
        "session_library_attachments",
        sa.Column(
            "session_id",
            sa.Text(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "library_id",
            sa.Text(),
            sa.ForeignKey("document_libraries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attached_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("session_library_attachments")
    op.drop_index("idx_documents_library_id", table_name="documents")
    op.drop_table("documents")
    op.drop_table("document_libraries")
