"""The whole pipeline through the real worker, queues, events and database.

Fake LLM and fake GeM, so no credits; needs `docker compose up postgres redis`.
"""

import asyncio
from uuid import UUID

import pytest

from greenink.core.enums import AnalysisStatus, FindingStatus, LLMTask, Stage, StageState, Verdict
from greenink.core.settings import get_settings
from greenink.db import repos
from greenink.jobs.queue import JobName, QueueName
from greenink_worker.__main__ import run
from greenink_worker.wiring import Services
from tests.integration import BID_REF, FakeGem, fake_llm, make_services, migrate, seed_demo, tender

pytestmark = [pytest.mark.db, pytest.mark.redis]

REDIS_TEST_DB = 14


@pytest.fixture
def urls(scratch_database_url: str) -> tuple[str, str]:
    migrate(scratch_database_url)
    redis_url = get_settings().redis_url.rsplit("/", 1)[0] + f"/{REDIS_TEST_DB}"
    return scratch_database_url, redis_url


async def start(services: Services, company_id: UUID) -> UUID:
    async with services.sessions.begin() as session:
        analysis, created = await repos.find_or_create_analysis(
            session, tender().id, company_id, "profile-hash", services.requirements_version
        )
    assert created
    payload = {"tender_id": str(tender().id), "analysis_id": str(analysis.id)}
    await services.queue.enqueue(JobName.INGEST, f"gem:{BID_REF}", payload)
    await services.queue.enqueue(JobName.INTEL, str(analysis.id), {"analysis_id": str(analysis.id)})
    return analysis.id


async def wait_for(services: Services, analysis_id: UUID, intel: bool = True) -> None:
    status = None
    for _ in range(200):
        async with services.sessions() as session:
            analysis = await repos.get_analysis(session, analysis_id)
            prices = await repos.price_intel(session, analysis_id)
        assert analysis is not None
        status = analysis.status
        if analysis.status in (AnalysisStatus.DONE, AnalysisStatus.PARTIAL, AnalysisStatus.FAILED) and (
            prices or not intel
        ):
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"analysis still {status}")


def test_report_end_to_end(urls: tuple[str, str]) -> None:
    database_url, redis_url = urls

    async def scenario() -> None:
        llm = fake_llm()
        services = await make_services(database_url, redis_url, llm)
        stop = asyncio.Event()
        worker = asyncio.create_task(run(list(QueueName), services.settings, stop, services))
        try:
            company_id = await seed_demo(services)
            analysis_id = await start(services, company_id)
            await wait_for(services, analysis_id)

            async with services.sessions() as session:
                analysis = await repos.get_analysis(session, analysis_id)
                findings = await repos.findings(session, analysis_id)
                events = await repos.events_after(session, analysis_id)
                prices = await repos.price_intel(session, analysis_id)
                docs = await repos.tender_documents(session, tender().id)
                pages = await repos.get_pages(session, docs[0].document.id)
            assert analysis is not None
            assert analysis.status == AnalysisStatus.DONE
            # The invented clause never reaches the judge: 3 extracted, 2 verified, 2 findings.
            assert len(findings) == 2
            assert analysis.verdict == Verdict.SKIP
            bis = next(f for f in findings if f.status == FindingStatus.FAIL)
            assert analysis.verdict_rules[0].finding_ids == [bis.id]
            assert [p.page_no for p in pages] == [1, 2]
            assert prices[0].band_low == 1000
            stages = [(e.stage, e.state) for _, e in events]
            for expected in [
                (Stage.INGEST, StageState.DONE),
                (Stage.PARSE, StageState.DONE),
                (Stage.VERIFY, StageState.DONE),
                (Stage.JUDGE, StageState.DONE),
                (Stage.VERDICT, StageState.DONE),
                (Stage.INTEL, StageState.DONE),
            ]:
                assert expected in stages, expected
            verify_event = next(e for _, e in events if e.stage == Stage.VERIFY)
            assert verify_event.message == "3 requirements found; 2 verified on their cited page."

            # A second company on the same tender reuses the stored document and requirements.
            extract_calls = [task for task, _, _ in llm.calls if task == LLMTask.EXTRACT]
            other = await seed_demo(services)
            second = await start(services, other)
            await wait_for(services, second)
            assert isinstance(services.gem, FakeGem)
            assert services.gem.fetches == 1
            assert [task for task, _, _ in llm.calls if task == LLMTask.EXTRACT] == extract_calls

            # A fix is drafted on demand and stored on the finding.
            await services.queue.enqueue(JobName.FIX, str(bis.id), {"analysis_id": str(analysis_id)})
            for _ in range(100):
                async with services.sessions() as session:
                    stored = next(f for f in await repos.findings(session, analysis_id) if f.id == bis.id)
                if stored.fix:
                    break
                await asyncio.sleep(0.1)
            assert stored.fix is not None
            assert stored.fix.title == "Plan the BIS licence"
        finally:
            stop.set()
            await asyncio.wait_for(worker, timeout=15)
            await services.redis.flushdb()
            await services.aclose()

    asyncio.run(scenario())
