"""Liveness and readiness. The uptime monitor pings `/readyz`."""

import asyncio

from arq.connections import RedisSettings, create_pool
from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from greenink.core.api import HealthStatus, ReadyStatus
from greenink.core.enums import ErrorCode
from greenink.core.errors import GreenInkError
from greenink_api.errors import error_responses

router = APIRouter(tags=["health"])

CHECK_TIMEOUT_S = 2.0


@router.get("/healthz", response_model=HealthStatus, operation_id="healthz")
async def healthz() -> HealthStatus:
    return HealthStatus()


@router.get("/readyz", response_model=ReadyStatus, responses=error_responses(503), operation_id="readyz")
async def readyz(request: Request) -> ReadyStatus:
    engine: AsyncEngine = request.app.state.engine
    redis_url: str = request.app.state.settings.redis_url
    postgres, redis = await asyncio.gather(_check_postgres(engine), _check_redis(redis_url))
    checks = {"postgres": postgres, "redis": redis}
    if not all(checks.values()):
        failed = ", ".join(name for name, ok in checks.items() if not ok)
        raise GreenInkError(ErrorCode.NOT_READY, f"Not ready: {failed} unreachable.")
    return ReadyStatus(checks=checks)


async def _check_postgres(engine: AsyncEngine) -> bool:
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_S), engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


async def _check_redis(redis_url: str) -> bool:
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_S):
            settings = RedisSettings.from_dsn(redis_url)
            settings.conn_retries = 0
            redis = await create_pool(settings)
            try:
                await redis.ping()
            finally:
                await redis.aclose()
    except Exception:
        return False
    return True
