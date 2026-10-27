"""Per-requirement judging with the `judge` task (prompt: prompts/judge.v1.md).

Only verified requirements are judged. Every one of them gets a finding: if the model skips
one, it is reported as `unclear` rather than silently dropped.
"""

import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from greenink.analysis.extract import load_prompt
from greenink.core.enums import FindingStatus, LLMTask, Severity
from greenink.core.ids import new_id
from greenink.core.models import (
    CompanyProfile,
    Evidence,
    Finding,
    JudgedRequirement,
    JudgeResult,
    Requirement,
)
from greenink.llm.port import LLM, LLMInput

BATCH_SIZE = 10
"""Small batches judged in parallel: wall time is the slowest batch, not one long call."""


def bid_context(
    closes_at: datetime | None, facts: Mapping[str, str] | None = None, now: datetime | None = None
) -> str:
    """Whole days only, so the judge's input (and its cache key) is stable within a day."""
    lines = [f"{name}: {value}" for name, value in (facts or {}).items()]
    if closes_at is None:
        lines.append("Closing date: unknown.")
    else:
        days = max(int((closes_at - (now or datetime.now(UTC))).total_seconds() // 86_400), 0)
        lines.append(f"Closing date: {closes_at.date().isoformat()}. Days left: {days}.")
    return "\n".join(lines)


class LLMJudge:
    version = "judge.v1"

    def __init__(self, llm: LLM) -> None:
        self._llm = llm
        self._instructions = load_prompt(self.version)

    async def judge(
        self,
        analysis_id: UUID,
        requirements: list[Requirement],
        profile: CompanyProfile,
        closes_at: datetime | None,
        *,
        bid_facts: Mapping[str, str] | None = None,
    ) -> list[Finding]:
        verified = [r for r in requirements if r.verified]
        batches = [verified[i : i + BATCH_SIZE] for i in range(0, len(verified), BATCH_SIZE)]
        company = profile.model_dump_json(exclude_defaults=True)
        context = bid_context(closes_at, bid_facts)
        results = await asyncio.gather(
            *(self._judge_batch(analysis_id, batch, company, context) for batch in batches)
        )
        return [finding for batch in results for finding in batch]

    async def _judge_batch(
        self, analysis_id: UUID, batch: list[Requirement], company: str, context: str
    ) -> list[Finding]:
        listing = json.dumps(
            [
                {
                    "id": str(r.id),
                    "category": r.category.value,
                    "text": r.text,
                    "page_no": r.page_no,
                    "quote": r.quote,
                }
                for r in batch
            ],
            ensure_ascii=False,
        )
        result = await self._llm.run(
            LLMTask.JUDGE,
            LLMInput(
                instructions=self._instructions,
                data={"company": company, "requirements": listing, "bid": context},
            ),
            JudgeResult,
            analysis_id=analysis_id,
        )
        judged: dict[UUID, JudgedRequirement] = {}
        for item in result.output.findings:
            judged.setdefault(item.requirement_id, item)

        findings: list[Finding] = []
        for requirement in batch:
            judgement = judged.get(requirement.id)
            if judgement is None:
                findings.append(_unjudged(analysis_id, requirement))
                continue
            findings.append(
                Finding(
                    id=new_id(),
                    analysis_id=analysis_id,
                    requirement=requirement,
                    status=judgement.status,
                    severity=judgement.severity,
                    reason=judgement.reason,
                    evidence=judgement.evidence,
                    fixable_before_close=None
                    if judgement.status == FindingStatus.PASS
                    else judgement.fixable_before_close,
                )
            )
        return findings


def _unjudged(analysis_id: UUID, requirement: Requirement) -> Finding:
    return Finding(
        id=new_id(),
        analysis_id=analysis_id,
        requirement=requirement,
        status=FindingStatus.UNCLEAR,
        severity=Severity.MEDIUM,
        reason="The reviewer model did not return a judgement for this requirement; check it by hand.",
        evidence=Evidence(company_has="Not judged"),
    )
