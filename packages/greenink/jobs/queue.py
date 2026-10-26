"""Queue names and the arq-backed `JobQueue`."""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from greenink.core.enums import Stage


class QueueName(StrEnum):
    INGEST = "q.ingest"
    PARSE = "q.parse"
    EXTRACT = "q.extract"
    JUDGE = "q.judge"
    INTEL = "q.intel"
    TRIAGE = "q.triage"


STAGE_QUEUE: dict[Stage, QueueName] = {
    Stage.INGEST: QueueName.INGEST,
    Stage.PARSE: QueueName.PARSE,
    Stage.EXTRACT: QueueName.EXTRACT,
    Stage.VERIFY: QueueName.EXTRACT,  # inline in the extract worker
    Stage.JUDGE: QueueName.JUDGE,
    Stage.VERDICT: QueueName.JUDGE,  # inline in the judge worker
    Stage.INTEL: QueueName.INTEL,
    Stage.TRIAGE: QueueName.TRIAGE,
}

MAX_TRIES = 4
"""First attempt plus 3 retries with exponential backoff (SPEC "Failures")."""


class ArqJobQueue:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url

    async def enqueue(self, stage: Stage, key: str, payload: Mapping[str, Any]) -> None:
        raise NotImplementedError("TODO(lane-A): arq enqueue_job with _job_id=key on STAGE_QUEUE[stage]")
