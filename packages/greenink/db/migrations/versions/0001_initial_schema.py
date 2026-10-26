"""Initial schema: every table in SPEC "Data model", with its unique and cache keys.

Revision ID: 0001
Revises:
Create Date: 2026-10-26 16:09:12.789627
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("profile", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "demo",
                "docs",
                "url",
                name="company_source",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "verified_level",
            sa.Enum(
                "unverified",
                "partial",
                "documented",
                name="verified_level",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.String(length=64),
            nullable=True,
            comment="Owning anonymous session; NULL for the shared demo company.",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
    )
    op.create_index(op.f("ix_companies_session_id"), "companies", ["session_id"], unique=False)
    op.create_table(
        "tenders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "gem",
                "upload",
                name="tender_source",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("source_ref", sa.String(length=200), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("buyer", sa.Text(), nullable=True),
        sa.Column("value_inr", sa.Numeric(precision=16, scale=2), nullable=True),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("official_url", sa.Text(), nullable=True),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenders")),
        sa.UniqueConstraint("source", "source_ref", name=op.f("uq_tenders_source_source_ref")),
    )
    op.create_table(
        "analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "done",
                "partial",
                "failed",
                name="analysis_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "verdict",
            sa.Enum(
                "bid",
                "fix_then_bid",
                "skip",
                name="verdict",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("verdict_reason", sa.Text(), nullable=True),
        sa.Column(
            "verdict_rules",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("profile_hash", sa.String(length=64), nullable=False),
        sa.Column("requirements_version", sa.String(length=128), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_analyses_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            name=op.f("fk_analyses_tender_id_tenders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analyses")),
        sa.UniqueConstraint(
            "tender_id",
            "company_id",
            "profile_hash",
            "requirements_version",
            name=op.f("uq_analyses_tender_id_company_id_profile_hash_requirements_version"),
        ),
    )
    op.create_index(op.f("ix_analyses_company_id"), "analyses", ["company_id"], unique=False)
    op.create_table(
        "company_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "udyam_certificate",
                "gst_certificate",
                "turnover_certificate",
                "balance_sheet",
                "bis_licence",
                "iso_certificate",
                "type_test_report",
                "oem_authorisation",
                "experience_certificate",
                "startup_recognition",
                "other",
                name="company_document_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("blob_key", sa.Text(), nullable=False),
        sa.Column(
            "facts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_documents_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_documents")),
    )
    op.create_index(
        op.f("ix_company_documents_company_id"),
        "company_documents",
        ["company_id"],
        unique=False,
    )
    op.create_table(
        "tender_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("blob_key", sa.Text(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            name=op.f("fk_tender_documents_tender_id_tenders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tender_documents")),
        sa.UniqueConstraint("sha256", name=op.f("uq_tender_documents_sha256")),
    )
    op.create_index(
        op.f("ix_tender_documents_tender_id"),
        "tender_documents",
        ["tender_id"],
        unique=False,
    )
    op.create_table(
        "job_events",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
            comment="Also the SSE event id.",
        ),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column(
            "stage",
            sa.Enum(
                "ingest",
                "parse",
                "extract",
                "verify",
                "judge",
                "verdict",
                "intel",
                "triage",
                name="stage",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.Enum(
                "queued",
                "running",
                "retrying",
                "done",
                "skipped",
                "failed",
                name="stage_state",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("fk_job_events_analysis_id_analyses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_events")),
    )
    op.create_index(
        op.f("ix_job_events_analysis_id_id"),
        "job_events",
        ["analysis_id", "id"],
        unique=False,
    )
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=True),
        sa.Column(
            "task",
            sa.Enum(
                "triage",
                "profile_url",
                "extract",
                "page_vision",
                "judge",
                "fix",
                name="llm_task",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ok",
                "cached",
                "invalid_output",
                "timeout",
                "error",
                "budget_exceeded",
                name="llm_call_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("fk_llm_calls_analysis_id_analyses"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_calls")),
    )
    op.create_index(op.f("ix_llm_calls_analysis_id"), "llm_calls", ["analysis_id"], unique=False)
    op.create_index(op.f("ix_llm_calls_created_at"), "llm_calls", ["created_at"], unique=False)
    op.create_index(op.f("ix_llm_calls_prompt_hash"), "llm_calls", ["prompt_hash"], unique=False)
    op.create_table(
        "pages",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "method",
            sa.Enum(
                "text",
                "vision",
                name="page_method",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.CheckConstraint("page_no >= 1", name=op.f("ck_pages_page_no_positive")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["tender_documents.id"],
            name=op.f("fk_pages_document_id_tender_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_id", "page_no", name=op.f("pk_pages")),
    )
    op.create_table(
        "price_intel",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("item", sa.Text(), nullable=False),
        sa.Column("band_low", sa.Numeric(precision=16, scale=2), nullable=True),
        sa.Column("band_high", sa.Numeric(precision=16, scale=2), nullable=True),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("fk_price_intel_analysis_id_analyses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_intel")),
        sa.UniqueConstraint("analysis_id", "item", name=op.f("uq_price_intel_analysis_id_item")),
    )
    op.create_table(
        "requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "turnover",
                "experience",
                "mse_exemption",
                "startup_exemption",
                "oem_authorisation",
                "bis_certification",
                "type_test",
                "emd",
                "epbg",
                "document",
                "delivery",
                "atc",
                "boq_format",
                "other",
                name="requirement_category",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("page_no >= 1", name=op.f("ck_requirements_page_no_positive")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["tender_documents.id"],
            name=op.f("fk_requirements_document_id_tender_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirements")),
    )
    op.create_index(
        op.f("ix_requirements_document_id_extractor_version"),
        "requirements",
        ["document_id", "extractor_version"],
        unique=False,
    )
    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pass",
                "fail",
                "missing_proof",
                "unclear",
                name="finding_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "critical",
                "high",
                "medium",
                "low",
                name="severity",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fixable_before_close", sa.Boolean(), nullable=True),
        sa.Column("fix", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("fk_findings_analysis_id_analyses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_findings_requirement_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_findings")),
        sa.UniqueConstraint(
            "analysis_id",
            "requirement_id",
            name=op.f("uq_findings_analysis_id_requirement_id"),
        ),
    )
    op.create_index(op.f("ix_findings_requirement_id"), "findings", ["requirement_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_findings_requirement_id"), table_name="findings")
    op.drop_table("findings")
    op.drop_index(op.f("ix_requirements_document_id_extractor_version"), table_name="requirements")
    op.drop_table("requirements")
    op.drop_table("price_intel")
    op.drop_table("pages")
    op.drop_index(op.f("ix_llm_calls_prompt_hash"), table_name="llm_calls")
    op.drop_index(op.f("ix_llm_calls_created_at"), table_name="llm_calls")
    op.drop_index(op.f("ix_llm_calls_analysis_id"), table_name="llm_calls")
    op.drop_table("llm_calls")
    op.drop_index(op.f("ix_job_events_analysis_id_id"), table_name="job_events")
    op.drop_table("job_events")
    op.drop_index(op.f("ix_tender_documents_tender_id"), table_name="tender_documents")
    op.drop_table("tender_documents")
    op.drop_index(op.f("ix_company_documents_company_id"), table_name="company_documents")
    op.drop_table("company_documents")
    op.drop_index(op.f("ix_analyses_company_id"), table_name="analyses")
    op.drop_table("analyses")
    op.drop_table("tenders")
    op.drop_index(op.f("ix_companies_session_id"), table_name="companies")
    op.drop_table("companies")
