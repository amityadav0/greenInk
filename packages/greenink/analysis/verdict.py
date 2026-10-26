"""The verdict, computed by code from findings, never by a model (SPEC "Verdict rules")."""

from dataclasses import dataclass

from greenink.core.enums import Verdict
from greenink.core.models import Finding, VerdictRule


@dataclass(frozen=True)
class VerdictOutcome:
    verdict: Verdict
    reason: str
    rules: list[VerdictRule]


def decide(findings: list[Finding]) -> VerdictOutcome:
    # TODO(lane-A): critical unfixable fail -> skip; fixable critical/high fail or missing
    # proof -> fix_then_bid; else bid. Every rule cites its findings. Unit-test every rule.
    raise NotImplementedError("TODO(lane-A): verdict rules")
