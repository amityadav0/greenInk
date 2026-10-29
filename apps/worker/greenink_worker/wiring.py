"""Composition root for the worker: builds every adapter once per process."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from arq.connections import ArqRedis, RedisSettings, create_pool
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from greenink.analysis.extract import LLMExtractor
from greenink.analysis.fixes import LLMFixer
from greenink.analysis.judge import LLMJudge
from greenink.analysis.port import Extractor, Fixer, Judge, Verifier
from greenink.analysis.verify import FuzzyQuoteVerifier
from greenink.companies.from_url import TavilyProfileBuilder
from greenink.companies.port import DocumentReader, WebsiteProfiler
from greenink.companies.profile import DocumentProfileBuilder
from greenink.core.settings import Settings
from greenink.db.session import make_engine, make_sessionmaker
from greenink.docs.parse import PyMuPDFParser
from greenink.docs.port import Parser
from greenink.intel.port import IntelProvider
from greenink.intel.tavily import TavilyIntelProvider
from greenink.jobs.events import RedisEventBus
from greenink.jobs.port import EventBus, JobQueue
from greenink.jobs.queue import ArqJobQueue
from greenink.llm.gateway import TokenFactoryGateway, make_client
from greenink.llm.router import load_models_config
from greenink.llm.trace import SqlTraceStore
from greenink.sources.base import SourceAdapter
from greenink.sources.config import load_sources_config
from greenink.sources.gem import RateLimiter, gem_adapter
from greenink.storage.blob import S3BlobStore
from greenink.storage.port import BlobStore
from greenink.triage.port import Triage
from greenink.triage.score import LLMTriage


@dataclass
class Services:
    """Everything a job handler needs, typed by port so tests can swap in fakes."""

    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    redis: ArqRedis
    queue: JobQueue
    events: EventBus
    blobs: BlobStore
    gem: SourceAdapter
    parser: Parser
    extractor: Extractor
    verifier: Verifier
    judge: Judge
    fixer: Fixer
    triage: Triage
    intel: IntelProvider | None
    website: WebsiteProfiler | None
    documents: DocumentReader
    closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    @property
    def requirements_version(self) -> str:
        return self.extractor.version

    async def aclose(self) -> None:
        for close in self.closers:
            await close()
        await self.redis.aclose()
        await self.engine.dispose()


def blob_store(settings: Settings) -> S3BlobStore:
    return S3BlobStore(
        settings.r2_endpoint_url,
        settings.r2_bucket,
        settings.r2_access_key_id or SecretStr(""),
        settings.r2_secret_access_key or SecretStr(""),
        settings.r2_addressing_style,
    )


async def build(settings: Settings) -> Services:
    if settings.nebius_api_key is None:
        raise RuntimeError("NEBIUS_API_KEY is not set")
    engine = make_engine(settings.database_url)
    sessions = make_sessionmaker(engine)
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    models = load_models_config(settings.config_dir / "models.yaml")
    sources = load_sources_config(settings.config_dir / "sources.yaml")
    llm = TokenFactoryGateway(models, make_client(models, settings.nebius_api_key), SqlTraceStore(sessions))
    tavily = settings.tavily_api_key
    blobs = blob_store(settings)
    await blobs.ensure_bucket()
    gem_config = sources.adapters.gem
    gem = gem_adapter(gem_config, RateLimiter(gem_config.rate_limit_rps, redis), settings)
    return Services(
        settings=settings,
        engine=engine,
        sessions=sessions,
        redis=redis,
        queue=ArqJobQueue(redis),
        events=RedisEventBus(sessions, redis),
        blobs=blobs,
        gem=gem,
        parser=PyMuPDFParser(llm),
        extractor=LLMExtractor(llm),
        verifier=FuzzyQuoteVerifier(),
        judge=LLMJudge(llm),
        fixer=LLMFixer(llm),
        triage=LLMTriage(llm),
        intel=TavilyIntelProvider(tavily, llm) if tavily else None,
        website=TavilyProfileBuilder(llm, tavily) if tavily else None,
        documents=DocumentProfileBuilder(llm),
        closers=[gem.aclose],
    )
