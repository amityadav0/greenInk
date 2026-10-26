"""Job handlers, one per queue. Each is idempotent on its key (SPEC "Pipeline and jobs").

Handlers wire adapters to ports; the domain logic lives in `greenink.*`.
"""

from collections.abc import Callable, Coroutine
from typing import Any

from greenink.jobs.queue import QueueName

Handler = Callable[[dict[str, Any], str, dict[str, Any]], Coroutine[Any, Any, None]]


async def ingest(ctx: dict[str, Any], key: str, payload: dict[str, Any]) -> None:
    """Key `source:source_ref`. Download, hash, store the blob; then parse."""
    raise NotImplementedError("TODO(lane-C): fetch via SourceAdapter, store via BlobStore")


async def parse(ctx: dict[str, Any], key: str, payload: dict[str, Any]) -> None:
    """Key `sha256`. Page text, vision for near-empty pages; then extract."""
    raise NotImplementedError("TODO(lane-A): Parser.parse, store pages")


async def extract(ctx: dict[str, Any], key: str, payload: dict[str, Any]) -> None:
    """Key `sha256:extractor_version`. Extract, then verify inline; then judge."""
    raise NotImplementedError("TODO(lane-A): Extractor + Verifier")


async def judge(ctx: dict[str, Any], key: str, payload: dict[str, Any]) -> None:
    """Key `analysis_id`. Judge verified requirements, draft fixes, then the verdict inline."""
    raise NotImplementedError("TODO(lane-A): Judge + Fixer + verdict.decide")


async def intel(ctx: dict[str, Any], key: str, payload: dict[str, Any]) -> None:
    """Key `analysis_id`. Price band from Tavily and GeM results."""
    raise NotImplementedError("TODO(lane-A): IntelProvider.prices")


async def triage(ctx: dict[str, Any], key: str, payload: dict[str, Any]) -> None:
    """Key `query_hash:company_id`. Badges for search results, in batches of 20."""
    raise NotImplementedError("TODO(lane-A): Triage.score")


HANDLERS: dict[QueueName, Handler] = {
    QueueName.INGEST: ingest,
    QueueName.PARSE: parse,
    QueueName.EXTRACT: extract,
    QueueName.JUDGE: judge,
    QueueName.INTEL: intel,
    QueueName.TRIAGE: triage,
}
