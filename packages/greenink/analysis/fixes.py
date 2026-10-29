"""Drafted fixes for failing findings, with the `fix` task (prompt: prompts/fix.v2.md)."""

from uuid import UUID

from greenink.analysis.extract import load_prompt
from greenink.core.enums import LLMTask
from greenink.core.models import CompanyProfile, Finding, Fix
from greenink.llm.port import LLM, LLMInput


class LLMFixer:
    version = "fix.v2"

    def __init__(self, llm: LLM) -> None:
        self._llm = llm
        self._instructions = load_prompt(self.version)

    async def draft(
        self, finding: Finding, profile: CompanyProfile, *, analysis_id: UUID | None = None
    ) -> Fix:
        result = await self._llm.run(
            LLMTask.FIX,
            LLMInput(
                instructions=self._instructions,
                data={
                    "finding": finding.model_dump_json(
                        include={"requirement", "status", "severity", "reason", "evidence"}
                    ),
                    "company": profile.model_dump_json(exclude_defaults=True),
                },
            ),
            Fix,
            analysis_id=analysis_id or finding.analysis_id,
        )
        return result.output
