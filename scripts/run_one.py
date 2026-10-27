"""Run the whole pipeline on one bid PDF and print a cited report with its Model Trace.

    make run-one BID=GEM-2026-B-8175711              # finds data/raw/**/GEM-2026-B-8175711.pdf
    make run-one BID=path/to/bid.pdf ARGS="--fixes 2"

Judges against the fictional Brightline Electricals profile unless --company is given.
Model calls are recorded in Postgres when DATABASE_URL is reachable, so a rerun of the same
bid is served from the prompt cache at no cost.
"""

import argparse
import asyncio
import hashlib
import json
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

from pydantic import SecretStr
from sqlalchemy import text

from greenink.analysis.extract import LLMExtractor
from greenink.analysis.fixes import LLMFixer
from greenink.analysis.judge import LLMJudge
from greenink.analysis.verdict import decide
from greenink.analysis.verify import FuzzyQuoteVerifier
from greenink.core.enums import FindingStatus, LLMCallStatus, Severity
from greenink.core.errors import GreenInkError
from greenink.core.models import CompanyProfile, LLMCall
from greenink.core.settings import get_settings
from greenink.db.session import make_engine, make_sessionmaker
from greenink.docs.parse import PyMuPDFParser
from greenink.llm.gateway import TokenFactoryGateway, make_client
from greenink.llm.router import load_models_config
from greenink.llm.trace import InMemoryTraceStore, SqlTraceStore, TraceStore

REPO = Path(__file__).resolve().parents[1]
IST = ZoneInfo("Asia/Kolkata")
SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
STATUS_MARK = {
    FindingStatus.FAIL: "FAIL",
    FindingStatus.MISSING_PROOF: "PROOF?",
    FindingStatus.UNCLEAR: "UNCLEAR",
    FindingStatus.PASS: "pass",
}


class RunTrace:
    """Passes calls to the real store and keeps this run's calls for the printed trace."""

    def __init__(self, inner: TraceStore) -> None:
        self.inner = inner
        self.calls: list[LLMCall] = []

    async def record(self, call: LLMCall, output: dict[str, Any] | None, error: str | None = None) -> None:
        self.calls.append(call)
        # The run's analysis id only keys its budget; there is no analyses row to point at.
        await self.inner.record(call.model_copy(update={"analysis_id": None}), output, error)

    async def find_cached(self, prompt_hash: str) -> dict[str, Any] | None:
        return await self.inner.find_cached(prompt_hash)

    async def spent_today_usd(self) -> float:
        return await self.inner.spent_today_usd()

    async def spent_for_analysis_usd(self, analysis_id: UUID) -> float:
        return sum(c.cost_usd for c in self.calls if c.analysis_id == analysis_id)


def find_bid(bid: str) -> Path:
    path = Path(bid)
    if path.is_file():
        return path
    name = bid.replace("/", "-") + ("" if bid.endswith(".pdf") else ".pdf")
    matches = sorted((REPO / "data" / "raw").rglob(name))
    if not matches:
        raise SystemExit(f"No PDF named {name} under data/raw/. Run `make gem-spike` first.")
    return matches[0]


def bid_index(pdf: Path) -> dict[str, Any]:
    """This bid's entry in the spike's index.json next to the PDF, when present."""
    index = pdf.parent / "index.json"
    if index.is_file():
        for bid in json.loads(index.read_text(encoding="utf-8")):
            if bid["bid_number"].replace("/", "-") == pdf.stem:
                entry: dict[str, Any] = bid
                return entry
    return {}


def closing_date(bid: dict[str, Any]) -> datetime | None:
    if not bid.get("end_date"):
        return None
    return datetime.strptime(bid["end_date"], "%Y-%m-%d %H:%M IST").replace(tzinfo=IST)


def bid_facts(bid: dict[str, Any]) -> dict[str, str]:
    names = {"title": "Item", "quantity": "Total quantity", "buyer": "Buyer"}
    return {label: str(bid[key]) for key, label in names.items() if bid.get(key) not in (None, "")}


async def trace_store() -> tuple[TraceStore, str]:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        async with asyncio.timeout(3), engine.connect() as connection:
            await connection.execute(text("SELECT 1 FROM llm_calls LIMIT 1"))
    except Exception:
        await engine.dispose()
        return InMemoryTraceStore(), "in memory (no Postgres: reruns are not cached)"
    return SqlTraceStore(make_sessionmaker(engine)), "Postgres llm_calls (reruns are cached)"


async def run(
    args: argparse.Namespace, pdf: Path, data: bytes, profile: CompanyProfile, api_key: SecretStr
) -> int:
    settings = get_settings()
    config = load_models_config(settings.config_dir / "models.yaml")
    store, store_note = await trace_store()
    trace = RunTrace(store)
    llm = TokenFactoryGateway(config, make_client(config, api_key), trace)
    analysis_id = uuid4()  # per-run budget key; not stored as an analyses row
    bid = bid_index(pdf)
    closes_at = closing_date(bid)
    document_id = uuid5(NAMESPACE_URL, f"sha256:{hashlib.sha256(data).hexdigest()}")

    started = time.monotonic()
    pages = await PyMuPDFParser(llm).parse(data)
    extracted = await LLMExtractor(llm).extract(document_id, pages, analysis_id=analysis_id)
    checked = FuzzyQuoteVerifier().verify(extracted, pages)
    verified = [r for r in checked if r.verified]
    findings = await LLMJudge(llm).judge(analysis_id, verified, profile, closes_at, bid_facts=bid_facts(bid))
    outcome = decide(findings)
    gaps = sorted(
        (f for f in findings if f.status != FindingStatus.PASS),
        key=lambda f: (SEVERITY_ORDER[f.severity], f.requirement.page_no),
    )
    fixes = {}
    for finding in gaps[: args.fixes]:
        fixes[finding.id] = await LLMFixer(llm).draft(finding, profile, analysis_id=analysis_id)
    elapsed = time.monotonic() - started

    print(f"\n{pdf.name}  ({len(pages)} pages)  company: {profile.legal_name}")
    print(f"Closes: {closes_at.strftime('%d %b %Y %H:%M IST') if closes_at else 'unknown'}")
    print(f"\nVERDICT: {outcome.verdict.value.upper().replace('_', ' ')}  {outcome.reason}")
    print(
        f"\nRequirements: {len(extracted)} extracted, {len(verified)} verified on their cited page, "
        f"{len(extracted) - len(verified)} dropped by the verifier"
    )
    for finding in sorted(
        findings, key=lambda f: (f.status == FindingStatus.PASS, SEVERITY_ORDER[f.severity])
    ):
        req = finding.requirement
        mark = STATUS_MARK[finding.status]
        print(f"\n  [{mark:7}] {finding.severity.value:8} p.{req.page_no:<3} {req.category.value}")
        print(textwrap.indent(textwrap.fill(req.text, 96), "      "))
        print(textwrap.indent(textwrap.fill(f'"{req.quote}"', 96), "      > "))
        if finding.status != FindingStatus.PASS:
            print(textwrap.indent(textwrap.fill(f"Why: {finding.reason}", 96), "      "))
        if finding.id in fixes:
            fix = fixes[finding.id]
            print(f"      Fix ({fix.kind.value}): {fix.title}")
    if args.show_dropped:
        for req in (r for r in checked if not r.verified):
            print(f'\n  [DROPPED] p.{req.page_no} {req.text}\n      > "{req.quote}"')

    print(f"\nModel Trace  ({store_note})")
    for call in trace.calls:
        mark = "" if call.status == LLMCallStatus.OK else f"  [{call.status.value}]"
        print(
            f"  {call.task.value:12} {call.model:40} {call.tokens_in:>7} in {call.tokens_out:>6} out "
            f"${call.cost_usd:.4f} {call.latency_ms / 1000:5.1f}s{mark}"
        )
    total = sum(c.cost_usd for c in trace.calls)
    print(f"  {'total':12} {'':40} {'':>7}    {'':>6}     ${total:.4f} {elapsed:5.1f}s wall")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("bid", help="bid number (e.g. GEM-2026-B-8175711) or a PDF path")
    parser.add_argument("--company", default=str(REPO / "seed" / "brightline" / "profile.json"))
    parser.add_argument(
        "--fixes", type=int, default=0, help="draft fixes for the N worst gaps (costs credits)"
    )
    parser.add_argument(
        "--show-dropped", action="store_true", help="also list requirements the verifier dropped"
    )
    args = parser.parse_args()
    api_key = get_settings().nebius_api_key
    if api_key is None:
        print("NEBIUS_API_KEY is not set; put it in .env.")
        return 2
    pdf = find_bid(args.bid)
    profile = CompanyProfile.model_validate_json(Path(args.company).read_text(encoding="utf-8"))
    try:
        return asyncio.run(run(args, pdf, pdf.read_bytes(), profile, api_key))
    except GreenInkError as exc:
        print(f"FAIL {exc.code.value}: {exc.message}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
