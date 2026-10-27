"""Shared setup for end-to-end tests: real Postgres + Redis, fake LLM and fake GeM (no credits)."""

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pymupdf
from alembic import command
from alembic.config import Config
from arq.connections import RedisSettings, create_pool

from greenink.analysis.extract import LLMExtractor
from greenink.analysis.fixes import LLMFixer
from greenink.analysis.judge import LLMJudge
from greenink.analysis.verify import FuzzyQuoteVerifier
from greenink.companies.profile import DocumentProfileBuilder
from greenink.core.enums import CompanySource, TenderSource, VerifiedLevel
from greenink.core.ids import tender_id
from greenink.core.models import CompanyProfile, PriceIntel, PriceSource, Tender
from greenink.core.settings import Settings
from greenink.db import repos
from greenink.db.session import make_engine, make_sessionmaker
from greenink.docs.parse import PyMuPDFParser
from greenink.jobs.events import RedisEventBus
from greenink.jobs.queue import ArqJobQueue
from greenink.llm.port import LLMInput
from greenink.sources.base import SourceFile, TenderDoc
from greenink.storage.blob import MemoryBlobStore
from greenink.triage.score import LLMTriage
from greenink_worker.wiring import Services
from tests.conftest import REPO_ROOT
from tests.fakes import FakeLLM

BID_REF = "GEM/2026/B/0000042"
PAGE_1 = "Bid Details\nYears of Past Experience Required for same/similar service\n3 Year (s)"
PAGE_2 = "Certificates\nThe bidder must hold a valid BIS licence for the offered current transformers."
PROFILE = CompanyProfile(legal_name="Brightline Electricals", years_in_operation=6)


def bid_pdf() -> bytes:
    document = pymupdf.open()  # type: ignore[no-untyped-call]
    for text in (PAGE_1, PAGE_2):
        y = 72
        page = document.new_page()
        for line in text.splitlines():
            page.insert_text((72, y), line)
            y += 16
    data: bytes = document.tobytes()  # type: ignore[no-untyped-call]
    return data


class FakeGem:
    source = TenderSource.GEM

    def __init__(self) -> None:
        self.fetches = 0

    async def search(self, query: str) -> list[Tender]:
        return [tender()]

    async def fetch(self, tender: Tender) -> TenderDoc:
        self.fetches += 1
        return TenderDoc(
            tender, [SourceFile("bid.pdf", bid_pdf(), "application/pdf", "https://example.invalid/bid")]
        )


class FakeIntel:
    async def prices(self, analysis_id: Any, item: str, buyer: str | None) -> PriceIntel:
        return PriceIntel(
            analysis_id=analysis_id,
            item=item,
            band_low=1000,
            band_high=1400,
            sources=[
                PriceSource(title="Example award", url="https://example.invalid/award", provider="tavily")
            ],
        )


def tender() -> Tender:
    return Tender(
        id=tender_id(TenderSource.GEM.value, BID_REF),
        source=TenderSource.GEM,
        source_ref=BID_REF,
        title="11kV Current Transformer",
        buyer="Example Power Department",
        closes_at=datetime.now(UTC) + timedelta(days=10),
        official_url="https://example.invalid/bid",
        meta={"document_url": "https://example.invalid/bid", "quantity": 6},
    )


def fake_llm() -> FakeLLM:
    def extract(_: LLMInput) -> dict[str, Any]:
        return {
            "requirements": [
                {
                    "category": "experience",
                    "text": "At least 3 years of experience.",
                    "page_no": 1,
                    "quote": "Years of Past Experience Required for same/similar service 3 Year (s)",
                },
                {
                    "category": "bis_certification",
                    "text": "A valid BIS licence is required.",
                    "page_no": 2,
                    "quote": "The bidder must hold a valid BIS licence for the offered current transformers.",
                },
                {
                    "category": "other",
                    "text": "Invented clause that is not in the document.",
                    "page_no": 2,
                    "quote": "Bidders must have an office in every district of the state.",
                },
            ]
        }

    def judge(sent: LLMInput) -> dict[str, Any]:
        findings = []
        for item in json.loads(sent.data["requirements"]):
            failing = item["category"] == "bis_certification"
            findings.append(
                {
                    "requirement_id": item["id"],
                    "status": "fail" if failing else "pass",
                    "severity": "critical",
                    "reason": "No BIS licence in the profile." if failing else "6 years of operation.",
                    "evidence": {"company_has": "ISO only" if failing else "6 years", "quotes": []},
                    "fixable_before_close": False if failing else None,
                }
            )
        return {"findings": findings}

    def triage(sent: LLMInput) -> dict[str, Any]:
        return {
            "scores": [
                {"source_ref": b["source_ref"], "badge": {"level": "green", "reason": "Makes CTs."}}
                for b in json.loads(sent.data["bids"])
            ]
        }

    def fix(_: LLMInput) -> dict[str, Any]:
        return {
            "kind": "checklist",
            "title": "Plan the BIS licence",
            "body": "Cannot be fixed before closing.",
            "steps": ["Apply to BIS"],
        }

    return FakeLLM(extract=extract, judge=judge, triage=triage, fix=fix)


def migrate(database_url: str) -> None:
    config = Config(str(REPO_ROOT / "packages" / "greenink" / "db" / "alembic.ini"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(config, "head")
    finally:
        if previous is None:
            del os.environ["DATABASE_URL"]
        else:
            os.environ["DATABASE_URL"] = previous


async def make_services(
    database_url: str, redis_url: str, llm: FakeLLM | None = None, blobs: MemoryBlobStore | None = None
) -> Services:
    llm = llm or fake_llm()
    engine = make_engine(database_url)
    sessions = make_sessionmaker(engine)
    redis = await create_pool(RedisSettings.from_dsn(redis_url))
    settings = Settings(database_url=database_url, redis_url=redis_url)
    return Services(
        settings=settings,
        engine=engine,
        sessions=sessions,
        redis=redis,
        queue=ArqJobQueue(redis),
        events=RedisEventBus(sessions, redis),
        blobs=blobs or MemoryBlobStore(),
        gem=FakeGem(),
        parser=PyMuPDFParser(llm),
        extractor=LLMExtractor(llm),
        verifier=FuzzyQuoteVerifier(),
        judge=LLMJudge(llm),
        fixer=LLMFixer(llm),
        triage=LLMTriage(llm),
        intel=FakeIntel(),
        website=None,
        documents=DocumentProfileBuilder(llm),
    )


async def seed_demo(services: Services) -> UUID:
    company_id = uuid4()
    async with services.sessions.begin() as session:
        await repos.upsert_tenders(session, [tender()])
        await repos.save_company(
            session,
            company_id=company_id,
            name="Brightline Electricals",
            profile=PROFILE,
            source=CompanySource.DEMO,
            verified_level=VerifiedLevel.DOCUMENTED,
            session_id=None,
        )
    return company_id
