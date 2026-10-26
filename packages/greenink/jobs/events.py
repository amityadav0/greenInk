"""Progress events: `job_events` rows plus Redis pub/sub on `analysis:{id}`."""

from collections.abc import AsyncIterator
from uuid import UUID

from greenink.core.models import JobEvent


def analysis_channel(analysis_id: UUID) -> str:
    return f"analysis:{analysis_id}"


class RedisEventBus:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url

    async def publish(self, event: JobEvent) -> None:
        raise NotImplementedError("TODO(lane-A): insert job_events row, then PUBLISH")

    def subscribe(self, analysis_id: UUID, after: str | None = None) -> AsyncIterator[JobEvent]:
        raise NotImplementedError("TODO(lane-B): replay job_events after `after`, then SUBSCRIBE")
