"""Tender documents: where each came from, and which extractor version has processed it.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-27 11:40:23.667919
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tender_documents", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column(
        "tender_documents",
        sa.Column(
            "extracted_version",
            sa.String(length=64),
            nullable=True,
            comment="Extractor version that has processed this document, even if it found nothing.",
        ),
    )


def downgrade() -> None:
    op.drop_column("tender_documents", "extracted_version")
    op.drop_column("tender_documents", "source_url")
