"""LLM task `price_intel` (Lightning reads unit prices from Tavily results).

Enums are VARCHAR + CHECK, which autogenerate does not compare, so the constraint is
rewritten by hand.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = ("triage", "profile_url", "extract", "page_vision", "judge", "fix")
NEW = (*OLD, "price_intel")


def _replace(values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_llm_calls_llm_task"), "llm_calls", type_="check")
    allowed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint(op.f("ck_llm_calls_llm_task"), "llm_calls", f"task IN ({allowed})")


def upgrade() -> None:
    _replace(NEW)


def downgrade() -> None:
    op.execute("DELETE FROM llm_calls WHERE task = 'price_intel'")
    _replace(OLD)
