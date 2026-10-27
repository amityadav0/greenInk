"""Worker entrypoint: `greenink-worker --queues all` or `--queues ingest,parse`.

Runs one arq worker per queue in a single process, so the hackathon deploy can run every
queue in one process and later split them by changing only the start command.
"""

import argparse
import asyncio
import signal
from collections.abc import Sequence
from typing import cast

import structlog
from arq.connections import RedisSettings
from arq.typing import WorkerCoroutine
from arq.worker import Worker, func

from greenink.core.logging import configure_logging
from greenink.core.settings import Settings, get_settings
from greenink.jobs.queue import MAX_TRIES, QueueName
from greenink_worker.stages import handlers_for
from greenink_worker.wiring import Services, build

log = structlog.get_logger()

JOB_TIMEOUT_S = 240
"""A job that outlives this is cancelled and retried: a killed worker's job comes back."""
KEEP_RESULT_S = 0
"""No results kept: a job key blocks duplicates only while queued or running. A kept result
would refuse the same key afterwards, stranding a second analysis of the same tender.
Stages are idempotent on their stored output, so re-running a finished key is cheap."""


def parse_queues(value: str) -> list[QueueName]:
    """`all`, or a comma list of names with or without the `q.` prefix."""
    if value.strip() == "all":
        return list(QueueName)
    queues: list[QueueName] = []
    for raw in value.split(","):
        name = raw.strip()
        if not name:
            continue
        try:
            queue = QueueName(name if name.startswith("q.") else f"q.{name}")
        except ValueError:
            known = ", ".join(q.value.removeprefix("q.") for q in QueueName)
            raise argparse.ArgumentTypeError(f"unknown queue {name!r}; known: all, {known}") from None
        if queue not in queues:
            queues.append(queue)
    if not queues:
        raise argparse.ArgumentTypeError("no queues given")
    return queues


def build_worker(queue: QueueName, settings: Settings, services: Services | None = None) -> Worker:
    return Worker(
        # arq's WorkerCoroutine protocol takes *args/**kwargs; our handlers have fixed signatures.
        functions=[
            func(cast(WorkerCoroutine, handler), name=job.value)
            for job, handler in handlers_for(queue).items()
        ],
        queue_name=queue.value,
        redis_settings=RedisSettings.from_dsn(settings.redis_url),
        handle_signals=False,
        max_tries=MAX_TRIES,
        job_timeout=JOB_TIMEOUT_S,
        keep_result=KEEP_RESULT_S,
        ctx={"settings": settings, "services": services},
    )


async def run(
    queues: Sequence[QueueName],
    settings: Settings,
    stop: asyncio.Event | None = None,
    services: Services | None = None,
) -> None:
    """Run one arq worker per queue until SIGINT/SIGTERM (or `stop` is set).

    Raises if any queue worker exits on its own, e.g. when Redis is unreachable, so the
    process exits non-zero and the platform restarts it.
    """
    owned = services is None
    services = services or await build(settings)
    try:
        await _run(queues, settings, stop or asyncio.Event(), services)
    finally:
        if owned:
            await services.aclose()


async def _run(
    queues: Sequence[QueueName], settings: Settings, stop: asyncio.Event, services: Services
) -> None:
    workers = [build_worker(queue, settings, services) for queue in queues]
    loop = asyncio.get_running_loop()
    signals = (signal.SIGINT, signal.SIGTERM)
    for sig in signals:
        loop.add_signal_handler(sig, stop.set)

    log.info("worker_starting", queues=[q.value for q in queues])
    running = [asyncio.create_task(worker.async_run()) for worker in workers]
    stopped = asyncio.create_task(stop.wait())
    try:
        done, _ = await asyncio.wait([*running, stopped], return_when=asyncio.FIRST_COMPLETED)
    finally:
        for sig in signals:
            loop.remove_signal_handler(sig)

    if stopped not in done:
        stopped.cancel()
    log.info("worker_stopping")
    await asyncio.gather(*(worker.close() for worker in workers), return_exceptions=True)
    results = await asyncio.gather(*running, return_exceptions=True)
    errors = [
        r for r in results if isinstance(r, BaseException) and not isinstance(r, asyncio.CancelledError)
    ]
    if errors:
        raise errors[0]
    if stopped not in done:
        raise RuntimeError("a queue worker exited unexpectedly")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="greenink-worker", description=__doc__)
    parser.add_argument(
        "--queues", type=parse_queues, default=list(QueueName), help="all, or e.g. ingest,parse"
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.env != "local")
    asyncio.run(run(args.queues, settings))


if __name__ == "__main__":
    main()
