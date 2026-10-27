"""The verdict, computed by code from findings, never by a model (SPEC "Verdict rules").

1. Any critical fail that cannot be fixed before the bid closes -> skip.
2. Any critical or high fail, missing proof or unclear finding that can be fixed -> fix then bid.
   (`unclear` counts with missing proof: the company cannot yet show it complies.)
3. Otherwise -> bid.

Every rule that fires cites the findings that triggered it.
"""

from dataclasses import dataclass
from uuid import UUID

from greenink.core.enums import FindingStatus, Severity, Verdict
from greenink.core.models import Finding, VerdictRule

BLOCKING = frozenset({Severity.CRITICAL, Severity.HIGH})
GAPS = frozenset({FindingStatus.FAIL, FindingStatus.MISSING_PROOF, FindingStatus.UNCLEAR})


@dataclass(frozen=True)
class VerdictOutcome:
    verdict: Verdict
    reason: str
    rules: list[VerdictRule]


def decide(findings: list[Finding]) -> VerdictOutcome:
    unfixable = [
        f
        for f in findings
        if f.severity == Severity.CRITICAL
        and f.status == FindingStatus.FAIL
        and f.fixable_before_close is False
    ]
    fixable = [f for f in findings if f.severity in BLOCKING and f.status in GAPS and f not in unfixable]

    rules: list[VerdictRule] = []
    if unfixable:
        rules.append(
            VerdictRule(rule="critical_unfixable", verdict=Verdict.SKIP, finding_ids=_ids(unfixable))
        )
    if fixable:
        rules.append(VerdictRule(rule="fixable_gap", verdict=Verdict.FIX_THEN_BID, finding_ids=_ids(fixable)))

    if unfixable:
        return VerdictOutcome(Verdict.SKIP, _reason_skip(unfixable), rules)
    if fixable:
        return VerdictOutcome(Verdict.FIX_THEN_BID, _reason_fix(fixable), rules)
    rules.append(VerdictRule(rule="no_blocking_gap", verdict=Verdict.BID, finding_ids=[]))
    checked = len(findings)
    return VerdictOutcome(
        Verdict.BID, f"No critical or high-risk gaps in {checked} checked requirements.", rules
    )


def _ids(findings: list[Finding]) -> list[UUID]:
    return [f.id for f in findings]


def _reason_skip(findings: list[Finding]) -> str:
    first = findings[0].requirement
    more = f" and {len(findings) - 1} more" if len(findings) > 1 else ""
    return f"Can't be fixed before closing: {first.text} (page {first.page_no}){more}."


def _reason_fix(findings: list[Finding]) -> str:
    critical = sum(f.severity == Severity.CRITICAL for f in findings)
    noun = "gap" if len(findings) == 1 else "gaps"
    detail = f", {critical} critical" if critical else ""
    return f"Fix {len(findings)} {noun} before bidding{detail}; each has a cited clause and a fix."
