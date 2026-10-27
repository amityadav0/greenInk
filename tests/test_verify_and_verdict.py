"""The citation verifier and the verdict rules: the two places the product must not be wrong."""

from uuid import uuid4

import pytest

from greenink.analysis.verdict import decide
from greenink.analysis.verify import MATCH_THRESHOLD, FuzzyQuoteVerifier, normalise, quote_score
from greenink.core.enums import FindingStatus, PageMethod, RequirementCategory, Severity, Verdict
from greenink.core.models import Evidence, Finding, Requirement
from greenink.docs.port import ParsedPage

PAGE_1 = """बड ववरण/Bid Details
उ2हं/समान सेवा के िलए अपे56त वगत अनुभव के
वष%/Years of Past Experience Required for
same/similar service
1 Year (s)
मूल उपकरण िनमा%ता का औसत टन%ओवर (गत 3 वष1
का)/OEM Average Turnover (Last 3 Years)
1 Lakh (s)
"""
PAGE_4 = """ISO 9001: The bidder or the OEM of the offered products must have ISO 9001 certification.
The bidder is required to upload, along with the bid, all relevant certificates such as BIS licence, type test
certificate, approval certificates and other certificates as prescribed in the Product Specification"""
PAGES = [
    ParsedPage(page_no=1, text=PAGE_1, method=PageMethod.TEXT),
    ParsedPage(page_no=4, text=PAGE_4, method=PageMethod.TEXT),
]


def requirement(quote: str, page_no: int = 1, **extra: object) -> Requirement:
    return Requirement.model_validate(
        {
            "id": uuid4(),
            "document_id": uuid4(),
            "extractor_version": "extract.v1",
            "category": RequirementCategory.EXPERIENCE,
            "text": "t",
            "page_no": page_no,
            "quote": quote,
            "verified": False,
            **extra,
        }
    )


@pytest.mark.parametrize(
    ("quote", "page_no", "expected"),
    [
        # Label and value on separate lines, quoted with one space: verified.
        ("Years of Past Experience Required for same/similar service 1 Year (s)", 1, True),
        # Case and spacing differences are normalised away.
        ("OEM AVERAGE TURNOVER  (Last 3 Years)\n1 Lakh (s)", 1, True),
        # A long quote spanning a line break in the PDF.
        (
            "upload, along with the bid, all relevant certificates such as BIS licence, "
            "type test certificate",
            4,
            True,
        ),
        # One character slip in a long quote stays above the threshold.
        ("The bidder or the OEM of the offered products must have ISO 9001 certificaton.", 4, True),
        # Right text, wrong page: rejected.
        ("The bidder or the OEM of the offered products must have ISO 9001 certification.", 1, False),
        # Page that does not exist: rejected.
        ("Years of Past Experience Required for same/similar service", 9, False),
        # Invented clause: rejected.
        ("The bidder must hold a valid NABL accreditation for all testing laboratories.", 4, False),
        # Numbers changed: rejected.
        ("Years of Past Experience Required for same/similar service 5 Year (s) minimum", 1, False),
        # Too short to prove anything, even though it appears on the page.
        ("1 Year (s)", 1, False),
    ],
)
def test_verifier(quote: str, page_no: int, expected: bool) -> None:
    [checked] = FuzzyQuoteVerifier().verify([requirement(quote, page_no)], PAGES)
    assert checked.verified is expected, quote_score(quote, {1: PAGE_1, 4: PAGE_4}.get(page_no, ""))


def test_verifier_keeps_everything_but_the_flag() -> None:
    original = requirement("Years of Past Experience Required for same/similar service 1 Year (s)")
    [checked] = FuzzyQuoteVerifier().verify([original], PAGES)
    assert checked.model_dump(exclude={"verified"}) == original.model_dump(exclude={"verified"})
    assert checked.verified


def test_normalise_and_threshold() -> None:
    assert normalise("  A\n\tB  ") == "a b"
    assert MATCH_THRESHOLD == 90


def finding(status: FindingStatus, severity: Severity, fixable: bool | None = None) -> Finding:
    return Finding(
        id=uuid4(),
        analysis_id=uuid4(),
        requirement=requirement("Years of Past Experience Required", verified=True),
        status=status,
        severity=severity,
        reason="r",
        evidence=Evidence(company_has="x"),
        fixable_before_close=fixable,
    )


def test_bid_when_nothing_blocks() -> None:
    outcome = decide(
        [
            finding(FindingStatus.PASS, Severity.CRITICAL),
            finding(FindingStatus.FAIL, Severity.LOW, fixable=True),
            finding(FindingStatus.MISSING_PROOF, Severity.MEDIUM, fixable=True),
        ]
    )
    assert outcome.verdict == Verdict.BID
    assert [r.rule for r in outcome.rules] == ["no_blocking_gap"]


def test_bid_on_no_findings() -> None:
    assert decide([]).verdict == Verdict.BID


@pytest.mark.parametrize(
    ("status", "severity"),
    [
        (FindingStatus.FAIL, Severity.HIGH),
        (FindingStatus.FAIL, Severity.CRITICAL),
        (FindingStatus.MISSING_PROOF, Severity.CRITICAL),
        (FindingStatus.MISSING_PROOF, Severity.HIGH),
        (FindingStatus.UNCLEAR, Severity.HIGH),
    ],
)
def test_fix_then_bid_on_fixable_blocking_gap(status: FindingStatus, severity: Severity) -> None:
    gap = finding(status, severity, fixable=True)
    outcome = decide([finding(FindingStatus.PASS, Severity.HIGH), gap])
    assert outcome.verdict == Verdict.FIX_THEN_BID
    assert outcome.rules[0].rule == "fixable_gap"
    assert outcome.rules[0].finding_ids == [gap.id]


def test_critical_fail_of_unknown_fixability_is_fix_then_bid() -> None:
    assert (
        decide([finding(FindingStatus.FAIL, Severity.CRITICAL, fixable=None)]).verdict == Verdict.FIX_THEN_BID
    )


def test_skip_on_unfixable_critical_fail_and_cite_it() -> None:
    blocker = finding(FindingStatus.FAIL, Severity.CRITICAL, fixable=False)
    fixable = finding(FindingStatus.MISSING_PROOF, Severity.HIGH, fixable=True)
    outcome = decide([fixable, blocker])
    assert outcome.verdict == Verdict.SKIP
    assert outcome.rules[0].rule == "critical_unfixable"
    assert outcome.rules[0].finding_ids == [blocker.id]
    assert outcome.rules[1].finding_ids == [fixable.id], "lower rules that fired are still cited"
    assert "page 1" in outcome.reason


def test_unfixable_high_fail_is_not_a_skip() -> None:
    """SPEC: only a critical unfixable fail skips; a high one still needs fixing first."""
    assert decide([finding(FindingStatus.FAIL, Severity.HIGH, fixable=False)]).verdict == Verdict.FIX_THEN_BID
