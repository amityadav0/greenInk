"""Progress events: `job_events` rows plus Redis pub/sub on `analysis:{id}`."""

import json
from collections.abc import AsyncIterator
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from greenink.core.enums import Stage, StageState
from greenink.core.models import JobEvent
from greenink.db import repos


def analysis_channel(analysis_id: UUID) -> str:
    return f"analysis:{analysis_id}"


class RedisEventBus:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], redis: Redis) -> None:
        self._sessions = sessions
        self._redis = redis

    async def publish(self, analysis_id: UUID, stage: Stage, state: StageState, message: str) -> int:
        async with self._sessions.begin() as session:
            event_id, event = await repos.add_event(session, analysis_id, stage, state, message)
        payload = json.dumps({"id": event_id, "event": event.model_dump(mode="json")})
        await self._redis.publish(analysis_channel(analysis_id), payload)
        return event_id

    async def subscribe(self, analysis_id: UUID, after: int = 0) -> AsyncIterator[tuple[int, JobEvent]]:
        """Subscribe first, then replay stored events, so nothing published in between is lost."""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(analysis_channel(analysis_id))
        try:
            last = after
            async with self._sessions() as session:
                stored = await repos.events_after(session, analysis_id, after)
            for event_id, event in stored:
                last = event_id
                yield event_id, event
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if message is None:
                    continue
                data = json.loads(message["data"])
                if data["id"] <= last:
                    continue
                last = data["id"]
                yield last, JobEvent.model_validate(data["event"])
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()  # type: ignore[no-untyped-call]
