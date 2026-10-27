import argparse

import pytest

from greenink.core.enums import Stage
from greenink.core.settings import Settings
from greenink.jobs.queue import JOB_QUEUE, STAGE_QUEUE, JobName, QueueName
from greenink_worker.__main__ import build_worker, parse_queues
from greenink_worker.stages import HANDLERS


def test_all_means_every_queue() -> None:
    assert parse_queues("all") == list(QueueName)
    assert len(QueueName) == 6


def test_queue_list_accepts_short_and_prefixed_names() -> None:
    assert parse_queues("ingest, q.parse,ingest") == [QueueName.INGEST, QueueName.PARSE]


def test_unknown_queue_is_rejected() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="unknown queue 'render'"):
        parse_queues("render")


def test_every_job_has_a_handler_and_every_queue_has_work() -> None:
    assert set(HANDLERS) == set(JobName)
    assert {JOB_QUEUE[job] for job in JobName} == set(QueueName)
    assert set(STAGE_QUEUE) == set(Stage)


async def _build() -> None:
    worker = build_worker(QueueName.JUDGE, Settings())
    assert worker.queue_name == "q.judge"
    assert sorted(worker.functions) == ["fix", "judge"]


def test_build_worker() -> None:
    import asyncio

    asyncio.run(_build())
