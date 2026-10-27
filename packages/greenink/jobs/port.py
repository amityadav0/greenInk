"""Port of the `jobs` module: queued work and progress events."""

from collections.abc import AsyncIterator, Mapping
from typing import Any, Protocol
from uuid import UUID

from greenink.core.enums import Stage, StageState
from greenink.core.models import JobEvent
from greenink.jobs.queue import JobName


class JobQueue(Protocol):
    async def enqueue(self, job: JobName, key: str, payload: Mapping[str, Any]) -> bool:
        """Enqueue `job` on its queue. `key` is the idempotency key: while a job with the same
        key is queued or running, a second enqueue is refused and returns False."""
        ...


class EventBus(Protocol):
    async def publish(self, analysis_id: UUID, stage: Stage, state: StageState, message: str) -> int:
        """Store the event in `job_events`, publish it on `analysis:{id}`, return its id."""
        ...

    def subscribe(self, analysis_id: UUID, after: int = 0) -> AsyncIterator[tuple[int, JobEvent]]:
        """Stored events with id > `after` (an SSE `Last-Event-ID`), then live ones."""
        ...
