"""Errors, settings and contract validation in greenink.core."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from greenink.core.api import CompanyCreate, ErrorBody
from greenink.core.enums import ErrorCode
from greenink.core.errors import GreenInkError
from greenink.core.models import Requirement, TenderDocument, TurnoverYear
from greenink.core.settings import Settings


@pytest.mark.parametrize("code", list(ErrorCode))
def test_every_error_code_has_an_http_status(code: ErrorCode) -> None:
    error = GreenInkError(code, "message")
    assert 400 <= error.http_status < 600
    assert ErrorBody(code=code, message=error.message, retryable=error.retryable).code == code


def test_retryable_defaults_and_override() -> None:
    assert GreenInkError(ErrorCode.UPSTREAM_UNAVAILABLE, "x").retryable is True
    assert GreenInkError(ErrorCode.NOT_FOUND, "x").retryable is False
    assert GreenInkError(ErrorCode.NOT_FOUND, "x", retryable=True).retryable is True


def test_settings_read_env_and_hide_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
    monkeypatch.setenv("NEBIUS_API_KEY", "secret-value-123")
    monkeypatch.setenv("TAVILY_API_KEY", "")  # empty means unset
    settings = Settings.from_env()
    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/x"
    assert settings.nebius_api_key is not None
    assert settings.nebius_api_key.get_secret_value() == "secret-value-123"
    assert settings.tavily_api_key is None
    assert "secret-value-123" not in repr(settings)
    assert "secret-value-123" not in str(settings.model_dump())


def _requirement(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": str(uuid4()),
        "document_id": str(uuid4()),
        "extractor_version": "extract.v1",
        "category": "turnover",
        "text": "Turnover at least 1 lakh.",
        "page_no": 1,
        "quote": "OEM Average Turnover (Last 3 Years) 1 Lakh (s)",
        "verified": False,
    }
    return {**base, **overrides}


def test_requirement_valid() -> None:
    assert Requirement.model_validate(_requirement()).page_no == 1


@pytest.mark.parametrize(
    "overrides",
    [{"page_no": 0}, {"category": "price"}, {"surprise": "field"}, {"quote": None}],
)
def test_requirement_rejects_bad_input(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Requirement.model_validate(_requirement(**overrides))


def test_sha256_and_fiscal_year_patterns() -> None:
    doc = {"id": str(uuid4()), "tender_id": str(uuid4()), "filename": "bid.pdf"}
    TenderDocument.model_validate({**doc, "sha256": "a" * 64})
    with pytest.raises(ValidationError):
        TenderDocument.model_validate({**doc, "sha256": "A" * 64})
    TurnoverYear(fiscal_year="2024-25", amount_inr=1)
    with pytest.raises(ValidationError):
        TurnoverYear(fiscal_year="2024-2025", amount_inr=1)
    with pytest.raises(ValidationError):
        TurnoverYear(fiscal_year="2024-25", amount_inr=-1)


def test_company_create_needs_a_name() -> None:
    with pytest.raises(ValidationError):
        CompanyCreate.model_validate({"name": "", "profile": {"legal_name": "X"}})
