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
from greenink_worker.stages import HANDLERS

log = structlog.get_logger()

JOB_TIMEOUT_S = 300


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


def build_worker(queue: QueueName, settings: Settings) -> Worker:
    return Worker(
        # arq's WorkerCoroutine protocol takes *args/**kwargs; our handlers have fixed signatures.
        functions=[func(cast(WorkerCoroutine, HANDLERS[queue]), name=queue.value.removeprefix("q."))],
        queue_name=queue.value,
        redis_settings=RedisSettings.from_dsn(settings.redis_url),
        handle_signals=False,
        max_tries=MAX_TRIES,
        job_timeout=JOB_TIMEOUT_S,
        ctx={"settings": settings},
    )


async def run(queues: Sequence[QueueName], settings: Settings) -> None:
    workers = [build_worker(queue, settings) for queue in queues]
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    log.info("worker_starting", queues=[q.value for q in queues])
    running = [asyncio.create_task(worker.async_run()) for worker in workers]
    stopped = asyncio.create_task(stop.wait())
    done, _ = await asyncio.wait([*running, stopped], return_when=asyncio.FIRST_COMPLETED)

    if stopped not in done:
        # A worker exited on its own (e.g. Redis unreachable): fail loudly so the platform restarts us.
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
