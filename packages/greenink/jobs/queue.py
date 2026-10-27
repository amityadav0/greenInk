"""Queue names, job names and the arq-backed `JobQueue`."""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from arq.connections import ArqRedis

from greenink.core.enums import Stage


class QueueName(StrEnum):
    INGEST = "q.ingest"
    PARSE = "q.parse"
    EXTRACT = "q.extract"
    JUDGE = "q.judge"
    INTEL = "q.intel"
    TRIAGE = "q.triage"


class JobName(StrEnum):
    """Every job a worker runs. Pipeline stages first, then on-demand work."""

    INGEST = "ingest"
    PARSE = "parse"
    EXTRACT = "extract"
    JUDGE = "judge"
    INTEL = "intel"
    TRIAGE = "triage"
    FIX = "fix"
    COMPANY_FROM_URL = "company_from_url"
    COMPANY_DOCUMENT = "company_document"


JOB_QUEUE: dict[JobName, QueueName] = {
    JobName.INGEST: QueueName.INGEST,
    JobName.PARSE: QueueName.PARSE,
    JobName.EXTRACT: QueueName.EXTRACT,
    JobName.JUDGE: QueueName.JUDGE,
    JobName.INTEL: QueueName.INTEL,
    JobName.TRIAGE: QueueName.TRIAGE,
    JobName.FIX: QueueName.JUDGE,
    JobName.COMPANY_FROM_URL: QueueName.INTEL,
    JobName.COMPANY_DOCUMENT: QueueName.EXTRACT,
}

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


def job_id(job: JobName, key: str) -> str:
    return f"{job.value}:{key}"


class ArqJobQueue:
    def __init__(self, redis: ArqRedis) -> None:
        self._redis = redis

    async def enqueue(self, job: JobName, key: str, payload: Mapping[str, Any]) -> bool:
        queued = await self._redis.enqueue_job(
            job.value, key, dict(payload), _queue_name=JOB_QUEUE[job].value, _job_id=job_id(job, key)
        )
        return queued is not None
