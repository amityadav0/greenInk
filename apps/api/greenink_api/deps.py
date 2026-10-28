"""Shared API runtime: adapters built once per process, the anonymous session, rate limits."""

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

import structlog
from arq.connections import ArqRedis
from fastapi import Request, Response
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from greenink.core.enums import ErrorCode
from greenink.core.errors import GreenInkError
from greenink.core.settings import Settings
from greenink.db.session import make_engine, make_sessionmaker
from greenink.jobs.events import RedisEventBus
from greenink.jobs.port import EventBus, JobQueue
from greenink.jobs.queue import ArqJobQueue
from greenink.sources.base import SourceAdapter
from greenink.sources.config import SourcesConfig, load_sources_config
from greenink.sources.gem import GemBidplusAdapter, RateLimiter
from greenink.storage.blob import S3BlobStore
from greenink.storage.port import BlobStore

log = structlog.get_logger()

SESSION_COOKIE = "gi_session"
SESSION_MAX_AGE_S = 365 * 24 * 3600
LOCAL_SESSION_SECRET = "local-only-not-secret"  # noqa: S105  (dev fallback; production requires SESSION_SECRET)


@dataclass
class AppState:
    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    redis: ArqRedis
    queue: JobQueue
    events: EventBus
    blobs: BlobStore
    gem: SourceAdapter
    sources: SourcesConfig

    async def aclose(self) -> None:
        close = getattr(self.gem, "aclose", None)
        if close:
            await close()
        await self.redis.aclose()
        await self.engine.dispose()


async def build_state(settings: Settings) -> AppState:
    engine = make_engine(settings.database_url)
    # Lazy: the API starts even while Redis is down; /readyz reports it, routes fail cleanly.
    redis = ArqRedis.from_url(settings.redis_url)
    sources = load_sources_config(settings.config_dir / "sources.yaml")
    gem = sources.adapters.gem
    return AppState(
        settings=settings,
        engine=engine,
        sessions=make_sessionmaker(engine),
        redis=redis,
        queue=ArqJobQueue(redis),
        events=RedisEventBus(make_sessionmaker(engine), redis),
        blobs=S3BlobStore(
            settings.r2_endpoint_url,
            settings.r2_bucket,
            settings.r2_access_key_id or SecretStr(""),
            settings.r2_secret_access_key or SecretStr(""),
            settings.r2_addressing_style,
        ),
        gem=GemBidplusAdapter(
            gem,
            RateLimiter(gem.rate_limit_rps, redis),
            proxy=settings.gem_proxy_url.get_secret_value() if settings.gem_proxy_url else None,
        ),
        sources=sources,
    )


def state(request: Request) -> AppState:
    app_state: AppState = request.app.state.services
    return app_state


# Anonymous session: a random id in an HMAC-signed cookie. No login for judges.


def _secret(settings: Settings) -> bytes:
    if settings.session_secret is not None:
        return settings.session_secret.get_secret_value().encode()
    if settings.env != "local":
        raise RuntimeError("SESSION_SECRET must be set outside local development")
    return LOCAL_SESSION_SECRET.encode()


def _sign(value: str, secret: bytes) -> str:
    digest = hmac.new(secret, value.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:32]


def read_session(cookie: str | None, secret: bytes) -> str | None:
    if not cookie or "." not in cookie:
        return None
    value, signature = cookie.rsplit(".", 1)
    return value if hmac.compare_digest(signature, _sign(value, secret)) else None


def session_id(request: Request, response: Response) -> str:
    """The caller's session id; issues a signed cookie on first visit."""
    settings: Settings = request.app.state.settings
    secret = _secret(settings)
    existing = read_session(request.cookies.get(SESSION_COOKIE), secret)
    if existing:
        return existing
    new = secrets.token_urlsafe(18)
    response.set_cookie(
        SESSION_COOKIE,
        f"{new}.{_sign(new, secret)}",
        max_age=SESSION_MAX_AGE_S,
        httponly=True,
        samesite="lax",
        secure=settings.env != "local",
    )
    return new


# Rate limits, per client IP, in Redis fixed windows.


@dataclass(frozen=True)
class Limit:
    name: str
    count: int
    window_s: int
    message: str


SEARCH_LIMIT = Limit("search", 60, 3600, "Too many searches from your network; try again in a few minutes.")
ANALYSIS_LIMIT = Limit(
    "analysis", 10, 3600, "You can start 10 new reports an hour; cached reports still open."
)
UPLOAD_LIMIT = Limit("upload", 10, 3600, "Too many uploads from your network; try again later.")
FIX_LIMIT = Limit("fix", 30, 3600, "Too many fix drafts from your network; try again later.")


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _exempt(request: Request) -> bool:
    token = state(request).settings.rate_limit_exempt_token
    sent = request.headers.get("x-greenink-admin")
    return token is not None and sent is not None and hmac.compare_digest(sent, token.get_secret_value())


async def check_limit(request: Request, limit: Limit) -> None:
    if _exempt(request):
        return
    redis: ArqRedis = state(request).redis
    window = int(time.time()) // limit.window_s
    key = f"rl:{limit.name}:{client_ip(request)}:{window}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, limit.window_s)
    if count > limit.count:
        log.info("rate_limited", limit=limit.name)
        raise GreenInkError(ErrorCode.RATE_LIMITED, limit.message)
