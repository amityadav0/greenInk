"""GeM bidplus spike: search live bids for a keyword and download their documents.

    uv run python scripts/gem_spike.py "current transformer" [--limit 10] [--out data/raw]

Flow, as the bidplus page does it:
  1. GET  /all-bids              -> session cookies + the `csrf_bd_gem_nk` token in the page
  2. POST /all-bids-data         -> form fields `payload` (JSON) and `csrf_bd_gem_nk`; 10 bids a page
  3. GET  /showbidDocument/{id}  -> the bid PDF (RA bids use other document paths)

Polite by design: at most 1 request a second and a user agent naming the project. Downloaded
files are untrusted; this script only saves them. Findings feed `greenink.sources.gem` (lane C).
"""

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://bidplus.gem.gov.in"
USER_AGENT = "GreenInk/0.1 (+https://github.com/amityadav0/greenInk; tender research tool)"
MIN_INTERVAL_S = 1.0
PAGE_SIZE = 10
CSRF_FIELD = "csrf_bd_gem_nk"
CSRF_RE = re.compile(rf"'{CSRF_FIELD}'\s*:\s*'([0-9a-f]+)'")

# Bid types and their document paths, as in the bidplus page's script.
DOCUMENT_PATHS = {5: "showdirectradocumentPdf", 2: "showradocumentPdf"}
DEFAULT_DOCUMENT_PATH = "showbidDocument"


@dataclass
class Bid:
    bid_number: str
    title: str
    buyer: str
    quantity: int | None
    end_date: str
    """As shown on GeM. GeM stores IST wall-clock time with a `Z` suffix, so this is IST."""
    document_url: str
    official_url: str


class PoliteClient:
    """httpx client that waits so requests are at least `MIN_INTERVAL_S` apart."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(30.0, connect=15.0),
            follow_redirects=True,
        )
        self._last = 0.0

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        wait = self._last + MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            return self._client.request(method, url, **kwargs)
        finally:
            self._last = time.monotonic()

    def close(self) -> None:
        self._client.close()


def csrf_token(client: PoliteClient) -> str:
    page = client.request("GET", "/all-bids")
    page.raise_for_status()
    match = CSRF_RE.search(page.text)
    if not match:
        raise RuntimeError("csrf token not found on /all-bids; the page layout may have changed")
    return match.group(1)


def search(client: PoliteClient, token: str, query: str, page: int) -> tuple[int, list[dict[str, Any]]]:
    payload = {
        "page": page,
        "param": {"searchBid": query, "searchType": "fullText"},
        "filter": {
            "bidStatusType": "ongoing_bids",
            "byType": "all",
            "highBidValue": "",
            "byEndDate": {"from": "", "to": ""},
            "sort": "Bid-End-Date-Oldest",
        },
    }
    response = client.request(
        "POST",
        "/all-bids-data",
        data={"payload": json.dumps(payload), CSRF_FIELD: token},
        headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{BASE_URL}/all-bids"},
    )
    response.raise_for_status()
    body = response.json()
    if body.get("code") != 200:
        raise RuntimeError(f"all-bids-data answered code {body.get('code')}: {str(body)[:200]}")
    result = body["response"]["response"]
    return int(result["numFound"]), list(result["docs"])


def to_bid(doc: dict[str, Any]) -> Bid:
    def first(value: Any) -> Any:
        return value[0] if isinstance(value, list) and value else value

    bid_id = first(doc.get("b_id"))
    bid_type = first(doc.get("b_bid_type"))
    path = DOCUMENT_PATHS.get(bid_type, DEFAULT_DOCUMENT_PATH)
    category = first(doc.get("b_category_name")) or ""
    boq_title = first(doc.get("bbt_title"))
    buyer_parts = [
        first(doc.get("ba_official_details_minName")),
        first(doc.get("ba_official_details_deptName")),
    ]
    quantity = first(doc.get("b_total_quantity"))
    document_url = f"{BASE_URL}/{path}/{bid_id}"
    return Bid(
        bid_number=str(first(doc.get("b_bid_number"))),
        title=f"{category} ({boq_title})" if boq_title else str(category),
        buyer=", ".join(str(part) for part in buyer_parts if part),
        quantity=int(quantity) if quantity is not None else None,
        end_date=_gem_time(first(doc.get("final_end_date_sort"))),
        document_url=document_url,
        official_url=document_url,
    )


def _gem_time(value: Any) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "")).strftime("%Y-%m-%d %H:%M IST")
    except ValueError:
        return str(value)


def download(client: PoliteClient, bid: Bid, out_dir: Path) -> str:
    response = client.request("GET", bid.document_url)
    if response.status_code != 200:
        return f"HTTP {response.status_code}"
    if not response.content.startswith(b"%PDF"):
        kind = response.headers.get("content-type", "unknown")
        return f"not a PDF ({kind}, {len(response.content)} bytes)"
    path = out_dir / (re.sub(r"[^A-Za-z0-9._-]+", "-", bid.bid_number).strip("-") + ".pdf")
    path.write_bytes(response.content)
    return f"saved {path} ({len(response.content) / 1024:.0f} KB)"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("query", help='keyword, e.g. "current transformer"')
    parser.add_argument("--limit", type=int, default=10, help="bids to print and download (default 10)")
    parser.add_argument("--out", type=Path, default=Path("data/raw"), help="download folder (git-ignored)")
    parser.add_argument("--no-download", action="store_true", help="search only")
    args = parser.parse_args()

    client = PoliteClient()
    try:
        started = time.monotonic()
        token = csrf_token(client)
        bids: list[Bid] = []
        total, page = 0, 1
        while len(bids) < args.limit:
            total, docs = search(client, token, args.query, page)
            bids.extend(to_bid(doc) for doc in docs)
            if len(docs) < PAGE_SIZE:
                break
            page += 1
        bids = bids[: args.limit]

        print(f"GeM bidplus: {total} ongoing bids match {args.query!r}; showing {len(bids)}\n")
        for n, bid in enumerate(bids, 1):
            print(f"{n:2}. {bid.bid_number}  closes {bid.end_date}")
            print(f"    title : {bid.title}")
            print(f"    buyer : {bid.buyer}")
            print(f"    qty   : {bid.quantity}")
            print(f"    doc   : {bid.document_url}")

        if args.no_download:
            return 0
        args.out.mkdir(parents=True, exist_ok=True)
        print(f"\nDownloading to {args.out}/ (1 request/second):")
        saved = 0
        for bid in bids:
            outcome = download(client, bid, args.out)
            saved += outcome.startswith("saved")
            print(f"  {bid.bid_number}: {outcome}")
        index = args.out / "index.json"
        index.write_text(json.dumps([asdict(b) for b in bids], indent=2) + "\n", encoding="utf-8")
        print(f"\n{saved}/{len(bids)} PDFs saved; index at {index}; {time.monotonic() - started:.0f}s total")
        return 0 if saved == len(bids) else 1
    except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as exc:
        print(f"FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
