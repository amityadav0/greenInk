"""Port of the `jobs` module: queued stages and progress events."""

from collections.abc import AsyncIterator, Mapping
from typing import Any, Protocol
from uuid import UUID

from greenink.core.enums import Stage
from greenink.core.models import JobEvent


class JobQueue(Protocol):
    async def enqueue(self, stage: Stage, key: str, payload: Mapping[str, Any]) -> None:
        """Enqueue `stage` on its queue. `key` is the stage's idempotency key: enqueueing
        the same key twice runs the job once."""
        ...


class EventBus(Protocol):
    async def publish(self, event: JobEvent) -> None:
        """Store the event in `job_events` and publish it on `analysis:{id}`."""
        ...

    def subscribe(self, analysis_id: UUID, after: str | None = None) -> AsyncIterator[JobEvent]:
        """Stored events after `after` (an SSE `Last-Event-ID`), then live ones."""
        ...
