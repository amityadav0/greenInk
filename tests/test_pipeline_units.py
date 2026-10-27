"""Parse, extract, judge and fix with a fake LLM and generated documents (no credits)."""

import asyncio
import io
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pymupdf
import pytest
from openpyxl import Workbook

from greenink.analysis.extract import CHUNK_CHARS, LLMExtractor, chunk_pages, render_pages
from greenink.analysis.fixes import LLMFixer
from greenink.analysis.judge import BATCH_SIZE, LLMJudge, bid_context
from greenink.core.enums import ErrorCode, FindingStatus, LLMTask, PageMethod, Severity
from greenink.core.errors import GreenInkError
from greenink.core.models import CompanyProfile, Evidence, Finding, Requirement
from greenink.docs.parse import PyMuPDFParser, sniff
from greenink.docs.port import ParsedPage
from greenink.llm.port import LLMInput
from tests.fakes import FakeLLM

PROFILE = CompanyProfile(legal_name="Brightline Electricals", business_nature_wording="Trading Business")


def pdf(*pages: str) -> bytes:
    document = pymupdf.open()  # type: ignore[no-untyped-call]
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    data: bytes = document.tobytes()  # type: ignore[no-untyped-call]
    return data


def test_sniff_by_bytes_not_name() -> None:
    assert sniff(pdf("x")) == "pdf"
    assert sniff(b"\x89PNG\r\n\x1a\n...") == "png"
    assert sniff(b"\xff\xd8\xff\xe0") == "jpeg"
    assert sniff(b"PK\x03\x04 not really a zip") == "unknown"
    assert sniff(b"<html>") == "unknown"


def test_parse_text_pages_and_send_only_empty_ones_to_vision() -> None:
    long_text = "Years of Past Experience Required for same/similar service 1 Year (s)"
    llm = FakeLLM(page_vision=lambda _: {"text": "Scanned: BIS licence IS 2705 required"})
    pages = asyncio.run(PyMuPDFParser(llm).parse(pdf(long_text, "", long_text)))

    assert [(p.page_no, p.method) for p in pages] == [
        (1, PageMethod.TEXT),
        (2, PageMethod.VISION),
        (3, PageMethod.TEXT),
    ]
    assert "Years of Past Experience" in pages[0].text
    assert pages[1].text.startswith("Scanned")
    [(task, sent, _)] = llm.calls
    assert task == LLMTask.PAGE_VISION
    assert sent.images[0].startswith(b"\x89PNG")


def test_vision_cap_limits_spend() -> None:
    llm = FakeLLM(page_vision=lambda _: {"text": "ok"})
    pages = asyncio.run(PyMuPDFParser(llm, max_vision_pages=2).parse(pdf("", "", "", "")))
    assert len(llm.calls) == 2
    assert [p.method for p in pages] == [PageMethod.VISION] * 2 + [PageMethod.TEXT] * 2


def test_unreadable_vision_page_is_kept_empty_but_budget_errors_propagate() -> None:
    def fail(_: LLMInput) -> dict[str, str]:
        raise GreenInkError(ErrorCode.UPSTREAM_UNAVAILABLE, "down")

    pages = asyncio.run(PyMuPDFParser(FakeLLM(page_vision=fail)).parse(pdf("")))
    assert pages[0].text == ""

    def broke(_: LLMInput) -> dict[str, str]:
        raise GreenInkError(ErrorCode.BUDGET_EXCEEDED, "spent")

    with pytest.raises(GreenInkError) as caught:
        asyncio.run(PyMuPDFParser(FakeLLM(page_vision=broke)).parse(pdf("")))
    assert caught.value.code == ErrorCode.BUDGET_EXCEEDED


def test_parse_xlsx_boq_one_page_per_sheet() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "BoQ"
    sheet.append(["Item", "Qty", "Unit rate"])
    sheet.append(["11kV CT 1200/5", 6, None])
    workbook.create_sheet("Notes").append(["Rates must be entered in this file only"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    pages = asyncio.run(PyMuPDFParser(FakeLLM()).parse(buffer.getvalue()))
    assert [p.page_no for p in pages] == [1, 2]
    assert pages[0].text.splitlines() == ["Sheet: BoQ", "Item | Qty | Unit rate", "11kV CT 1200/5 | 6"]
    assert "Rates must be entered" in pages[1].text


@pytest.mark.parametrize("data", [b"%PDF-1.7 truncated garbage", b"MZ\x90\x00 an exe"])
def test_bad_files_get_a_clear_error(data: bytes) -> None:
    with pytest.raises(GreenInkError) as caught:
        asyncio.run(PyMuPDFParser(FakeLLM()).parse(data))
    assert caught.value.code == ErrorCode.UNSUPPORTED_MEDIA_TYPE


def page(n: int, text: str) -> ParsedPage:
    return ParsedPage(page_no=n, text=text, method=PageMethod.TEXT)


def test_render_and_chunk_pages() -> None:
    assert render_pages([page(1, " a "), page(2, "b")]) == "=== PAGE 1 ===\na\n=== PAGE 2 ===\nb"
    big = [page(n, "x" * (CHUNK_CHARS // 2)) for n in range(1, 6)]
    chunks = chunk_pages(big)
    assert [len(c) for c in chunks] == [2, 2, 1]
    assert [p.page_no for c in chunks for p in c] == [1, 2, 3, 4, 5]


def test_extract_builds_requirements_and_dedupes_across_chunks() -> None:
    item = {
        "category": "experience",
        "text": "1 year",
        "page_no": 1,
        "quote": "Years of Past Experience 1 Year (s)",
    }
    llm = FakeLLM(
        extract=lambda _: {"requirements": [item, {**item, "quote": " years of past experience  1 year (s)"}]}
    )
    document_id, analysis_id = uuid4(), uuid4()
    pages = [page(1, "x" * (CHUNK_CHARS - 10)), page(2, "y" * 100), page(3, "   ")]
    requirements = asyncio.run(LLMExtractor(llm).extract(document_id, pages, analysis_id=analysis_id))

    assert len(llm.calls) == 2, "two chunks; the blank page is not sent"
    assert len(requirements) == 1
    [req] = requirements
    assert req.document_id == document_id
    assert req.extractor_version == "extract.v1"
    assert req.verified is False
    task, sent, sent_analysis = llm.calls[0]
    assert task == LLMTask.EXTRACT
    assert sent_analysis == analysis_id
    assert sent.data["tender"].startswith("=== PAGE 1 ===")
    assert "extract.v1" in sent.instructions


def test_extract_skips_documents_with_no_text() -> None:
    llm = FakeLLM()
    assert asyncio.run(LLMExtractor(llm).extract(uuid4(), [page(1, "")])) == []
    assert llm.calls == []


def req(verified: bool = True) -> Requirement:
    return Requirement(
        id=uuid4(),
        document_id=uuid4(),
        extractor_version="extract.v1",
        category="turnover",
        text="Turnover at least 50 lakh",
        page_no=1,
        quote="Bidder Turnover 50 Lakh (s)",
        verified=verified,
    )


def judged(requirement_id: UUID, status: str = "fail") -> dict[str, object]:
    return {
        "requirement_id": str(requirement_id),
        "status": status,
        "severity": "critical",
        "reason": "Turnover 48 lakh is below 50 lakh.",
        "evidence": {"company_has": "48 lakh in 2024-25", "quotes": []},
        "fixable_before_close": False,
    }


def test_judge_sends_only_verified_requirements_and_covers_every_one() -> None:
    good, skipped, unverified = req(), req(), req(verified=False)

    def respond(sent: LLMInput) -> dict[str, object]:
        ids = [item["id"] for item in json.loads(sent.data["requirements"])]
        assert str(unverified.id) not in ids
        # The model forgets one requirement and invents another id.
        return {"findings": [judged(good.id), judged(uuid4())]}

    llm = FakeLLM(judge=respond)
    analysis_id = uuid4()
    findings = asyncio.run(LLMJudge(llm).judge(analysis_id, [good, skipped, unverified], PROFILE, None))

    assert [f.requirement.id for f in findings] == [good.id, skipped.id]
    assert findings[0].status == FindingStatus.FAIL
    assert findings[0].severity == Severity.CRITICAL
    assert findings[0].fixable_before_close is False
    assert findings[1].status == FindingStatus.UNCLEAR, "a skipped requirement is never silently dropped"
    assert all(f.analysis_id == analysis_id for f in findings)
    sent = llm.calls[0][1]
    assert json.loads(sent.data["company"])["business_nature_wording"] == "Trading Business"


def test_judge_batches_and_pass_has_no_fixability() -> None:
    requirements = [req() for _ in range(BATCH_SIZE + 3)]
    llm = FakeLLM(
        judge=lambda sent: {
            "findings": [judged(item["id"], "pass") for item in json.loads(sent.data["requirements"])]
        }
    )
    findings = asyncio.run(LLMJudge(llm).judge(uuid4(), requirements, PROFILE, None))
    assert len(llm.calls) == 2
    assert len(findings) == BATCH_SIZE + 3
    assert all(f.fixable_before_close is None for f in findings)


def test_bid_context_days_left() -> None:
    now = datetime(2026, 10, 27, tzinfo=UTC)
    assert bid_context(now + timedelta(days=3, hours=5), now=now).endswith("Days left: 3.")
    assert bid_context(now - timedelta(days=1), now=now).endswith("Days left: 0.")
    assert bid_context(None) == "Closing date: unknown."
    with_facts = bid_context(None, {"Quantity": "6", "Title": "11kV CT"})
    assert with_facts.splitlines() == ["Quantity: 6", "Title: 11kV CT", "Closing date: unknown."]


def test_extracted_ids_are_deterministic_per_document() -> None:
    item = {"category": "turnover", "text": "t", "page_no": 1, "quote": "OEM Average Turnover 1 Lakh (s)"}
    llm = FakeLLM(extract=lambda _: {"requirements": [item]})
    document_id = uuid4()
    pages = [page(1, "OEM Average Turnover 1 Lakh (s)")]
    first = asyncio.run(LLMExtractor(llm).extract(document_id, pages))
    again = asyncio.run(LLMExtractor(llm).extract(document_id, pages))
    other = asyncio.run(LLMExtractor(llm).extract(uuid4(), pages))
    assert first[0].id == again[0].id
    assert first[0].id != other[0].id


def test_fixer_drafts_from_the_finding() -> None:
    llm = FakeLLM(
        fix=lambda _: {
            "kind": "letter",
            "title": "Ask your CA",
            "body": "Dear [CA name], ...",
            "steps": ["Send it"],
        }
    )
    finding = Finding(
        id=uuid4(),
        analysis_id=uuid4(),
        requirement=req(),
        status=FindingStatus.FAIL,
        severity=Severity.HIGH,
        reason="r",
        evidence=Evidence(company_has="x"),
    )
    fix = asyncio.run(LLMFixer(llm).draft(finding, PROFILE))
    assert fix.title == "Ask your CA"
    task, sent, analysis_id = llm.calls[0]
    assert task == LLMTask.FIX
    assert analysis_id == finding.analysis_id
    assert "Turnover at least 50 lakh" in sent.data["finding"]
