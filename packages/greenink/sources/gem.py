"""GeM bidplus adapter (bidplus.gem.gov.in). Request flow and page layout: docs/GEM_NOTES.md.

Polite by design: one request a second across every process (a Redis lock when available),
a user agent naming the project, retries with backoff, and a 25 MB cap per download.
"""

import asyncio
import json
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
import pymupdf
import structlog
from redis.asyncio import Redis

from greenink.core.enums import ErrorCode, TenderSource
from greenink.core.errors import GreenInkError
from greenink.core.ids import tender_id
from greenink.core.models import Tender
from greenink.core.settings import Settings
from greenink.sources.base import SourceFile, TenderDoc
from greenink.sources.config import GemConfig

log = structlog.get_logger()

IST = ZoneInfo("Asia/Kolkata")
CSRF_FIELD = "csrf_bd_gem_nk"
CSRF_RE = re.compile(rf"'{CSRF_FIELD}'\s*:\s*'([0-9a-f]+)'")
CSRF_TTL_S = 600
PAGE_SIZE = 10
SORT = "Bid-Start-Date-Latest"
DOCUMENT_PATHS = {5: "showdirectradocumentPdf", 2: "showradocumentPdf"}
MAX_BYTES = 25 * 1024 * 1024
MAX_ATTACHMENTS = 6
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

# Linked files that hold bid requirements. GTC, SLA and catalogue pages apply to every bid.
ATTACHMENT_PATTERNS = (
    re.compile(r"^https://mkp\.gem\.gov\.in/.*(buyer_documents|uploaded_documents)/"),
    re.compile(r"^https://bidplus\.gem\.gov\.in/resources/upload_nas/.*\.(xlsx|pdf)$", re.IGNORECASE),
)


class RelayTransport(httpx.AsyncBaseTransport):
    """Sends each request to the GeM relay (infra/gem-relay, Vercel Mumbai) with the real URL in
    `x-target-url`. The response is returned against the original request, so httpx's cookie
    jar and redirect handling behave exactly as if GeM had answered directly."""

    def __init__(self, relay_url: str, key: str, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._relay = httpx.URL(relay_url)
        self._key = key
        self._inner = inner or httpx.AsyncHTTPTransport(retries=1)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        headers = [(k, v) for k, v in request.headers.raw if k.lower() not in (b"host", b"content-length")]
        headers += [(b"x-target-url", str(request.url).encode()), (b"x-relay-key", self._key.encode())]
        relayed = httpx.Request(
            request.method,
            self._relay,
            headers=headers,
            content=await request.aread(),
            extensions=request.extensions,
        )
        response = await self._inner.handle_async_request(relayed)
        content = await response.aread()
        if response.status_code in (401, 403) and content in (b"unauthorised", b"target not allowed"):
            raise httpx.ConnectError(f"GeM relay refused the request: {content.decode()}", request=request)
        return httpx.Response(
            response.status_code,
            headers=[
                (k, v)
                for k, v in response.headers.raw
                if k.lower() not in (b"content-encoding", b"transfer-encoding", b"content-length")
            ],
            content=content,
            request=request,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()


class RateLimiter:
    """At most `rps` requests a second, shared across processes when Redis is given."""

    def __init__(self, rps: float, redis: Redis | None = None, key: str = "ratelimit:gem") -> None:
        self._interval = 1.0 / rps
        self._redis = redis
        self._key = key
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self) -> None:
        if self._redis is not None:
            # A cross-process lock: the slot is a Redis key that expires after one interval.
            slot_ms = int(self._interval * 1000)
            while True:
                if await self._redis.set(self._key, "1", nx=True, px=slot_ms):
                    return
                await asyncio.sleep(0.1)
        async with self._lock:
            delay = self._last + self._interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else value


def parse_csrf(html: str) -> str:
    match = CSRF_RE.search(html)
    if not match:
        raise GreenInkError(
            ErrorCode.UPSTREAM_UNAVAILABLE, "GeM changed its page layout; search is unavailable."
        )
    return match.group(1)


def parse_end(value: Any) -> datetime | None:
    """GeM stores IST wall-clock time with a `Z` suffix."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "")).replace(tzinfo=IST)
    except ValueError:
        return None


def to_tender(doc: dict[str, Any], base_url: str) -> Tender:
    bid_id = _first(doc.get("b_id"))
    bid_number = str(_first(doc.get("b_bid_number")))
    category = _first(doc.get("b_category_name")) or ""
    boq_title = _first(doc.get("bbt_title"))
    buyer = ", ".join(
        str(p)
        for p in (
            _first(doc.get("ba_official_details_minName")),
            _first(doc.get("ba_official_details_deptName")),
        )
        if p
    )
    quantity = _first(doc.get("b_total_quantity"))
    document_url = (
        f"{base_url}/{DOCUMENT_PATHS.get(_first(doc.get('b_bid_type')), 'showbidDocument')}/{bid_id}"
    )
    return Tender(
        id=tender_id(TenderSource.GEM.value, bid_number),
        source=TenderSource.GEM,
        source_ref=bid_number,
        title=f"{category} ({boq_title})" if boq_title else str(category),
        buyer=buyer or None,
        closes_at=parse_end(_first(doc.get("final_end_date_sort"))),
        official_url=document_url,
        meta={
            "b_id": bid_id,
            "document_url": document_url,
            "quantity": int(quantity) if quantity is not None else None,
        },
    )


def rank(tenders: list[Tender], query: str) -> list[Tender]:
    """Bids whose title contains the query first; GeM's full-text match is loose."""
    needle = " ".join(query.lower().split())
    return sorted(tenders, key=lambda t: needle not in " ".join(t.title.lower().split()))


def attachment_links(pdf: bytes) -> list[str]:
    try:
        document = pymupdf.open(stream=pdf, filetype="pdf")
    except Exception:
        return []
    links: list[str] = []
    with document:
        for index in range(document.page_count):
            for link in document[index].get_links():
                uri = link.get("uri") or ""
                if any(p.search(uri) for p in ATTACHMENT_PATTERNS) and uri not in links:
                    links.append(uri)
    return links[:MAX_ATTACHMENTS]


def content_type(data: bytes) -> str | None:
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"PK\x03\x04"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


class GemBidplusAdapter:
    source = TenderSource.GEM

    def __init__(
        self,
        config: GemConfig,
        limiter: RateLimiter,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Any = asyncio.sleep,
        proxy: str | None = None,
    ) -> None:
        """`proxy`: an HTTP(S) proxy on an Indian host. GeM refuses connections from many
        non-Indian IPs (confirmed from a US cloud host), so production routes GeM through one."""
        self._config = config
        self._base = str(config.base_url).rstrip("/")
        self._limiter = limiter
        self._sleep = sleep
        self._client = httpx.AsyncClient(
            transport=transport,
            proxy=proxy if transport is None else None,
            headers={"User-Agent": config.user_agent},
            timeout=httpx.Timeout(config.timeout_s, connect=15.0),
            follow_redirects=True,
        )
        self._token: tuple[str, float] | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        attempts = self._config.max_retries + 1
        for attempt in range(1, attempts + 1):
            await self._limiter.wait()
            try:
                response = await self._client.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                if attempt == attempts:
                    raise GreenInkError(
                        ErrorCode.UPSTREAM_UNAVAILABLE, "GeM is not responding right now."
                    ) from exc
            else:
                if response.status_code not in RETRY_STATUSES or attempt == attempts:
                    return response
            await self._sleep(2 ** (attempt - 1))
        raise AssertionError("unreachable")

    async def _csrf(self, refresh: bool = False) -> str:
        if self._token and not refresh and time.monotonic() - self._token[1] < CSRF_TTL_S:
            return self._token[0]
        page = await self._request("GET", f"{self._base}/all-bids")
        if page.status_code != 200:
            raise GreenInkError(ErrorCode.UPSTREAM_UNAVAILABLE, f"GeM answered HTTP {page.status_code}.")
        token = parse_csrf(page.text)
        self._token = (token, time.monotonic())
        return token

    async def _search_page(self, query: str, page: int) -> tuple[int, list[dict[str, Any]]]:
        payload = {
            "page": page,
            "param": {"searchBid": query, "searchType": "fullText"},
            "filter": {
                "bidStatusType": "ongoing_bids",
                "byType": "all",
                "highBidValue": "",
                "byEndDate": {"from": "", "to": ""},
                "sort": SORT,
            },
        }
        for refresh in (False, True):
            token = await self._csrf(refresh=refresh)
            response = await self._request(
                "POST",
                f"{self._base}/all-bids-data",
                data={"payload": json.dumps(payload), CSRF_FIELD: token},
                headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{self._base}/all-bids"},
            )
            if response.status_code in (403, 419) and not refresh:
                continue  # stale session token: fetch a fresh one once
            if response.status_code != 200:
                raise GreenInkError(
                    ErrorCode.UPSTREAM_UNAVAILABLE, f"GeM search answered HTTP {response.status_code}."
                )
            try:
                body = response.json()
                result = body["response"]["response"]
                return int(result["numFound"]), list(result["docs"])
            except (ValueError, KeyError, TypeError) as exc:
                raise GreenInkError(
                    ErrorCode.UPSTREAM_UNAVAILABLE, "GeM returned an unexpected search page."
                ) from exc
        raise AssertionError("unreachable")

    async def search(self, query: str) -> list[Tender]:
        pages = max(1, -(-self._config.max_results // PAGE_SIZE))
        tenders: list[Tender] = []
        for page in range(1, pages + 1):
            total, docs = await self._search_page(query, page)
            tenders.extend(to_tender(doc, self._base) for doc in docs)
            if len(docs) < PAGE_SIZE or page * PAGE_SIZE >= total:
                break
        unique = {t.id: t for t in tenders}
        return rank(list(unique.values()), query)[: self._config.max_results]

    async def _download(self, url: str) -> tuple[bytes, str] | None:
        response = await self._request("GET", url)
        if response.status_code != 200 or len(response.content) > MAX_BYTES:
            log.warning(
                "gem_download_skipped", url=url, status=response.status_code, size=len(response.content)
            )
            return None
        kind = content_type(response.content)
        if kind is None:
            log.warning("gem_download_not_a_document", url=url)
            return None
        return response.content, kind

    async def fetch(self, tender: Tender) -> TenderDoc:
        url = str(tender.meta.get("document_url") or tender.official_url or "")
        if not url:
            raise GreenInkError(ErrorCode.NOT_FOUND, "This bid has no document link.")
        main = await self._download(url)
        if main is None:
            raise GreenInkError(
                ErrorCode.UPSTREAM_UNAVAILABLE, "The bid document could not be downloaded from GeM."
            )
        stem = tender.source_ref.replace("/", "-")
        files = [SourceFile(f"{stem}.pdf", main[0], main[1], url)]
        for n, link in enumerate(await asyncio.to_thread(attachment_links, main[0]), start=1):
            downloaded = await self._download(link)
            if downloaded is None:
                continue
            extension = ".xlsx" if downloaded[1].endswith("sheet") else ".pdf"
            name = urlparse(link).path.rsplit("/", 1)[-1] or f"attachment-{n}"
            files.append(
                SourceFile(
                    f"{stem}-{n}-{name[:60]}{'' if name.endswith(extension) else extension}",
                    downloaded[0],
                    downloaded[1],
                    link,
                )
            )
        return TenderDoc(tender=tender, files=files)


def gem_adapter(config: GemConfig, limiter: RateLimiter, settings: Settings) -> GemBidplusAdapter:
    """The adapter with whichever route to GeM is configured: relay, proxy, or direct."""
    if settings.gem_relay_url and settings.gem_relay_key:
        relay = RelayTransport(settings.gem_relay_url, settings.gem_relay_key.get_secret_value())
        return GemBidplusAdapter(config, limiter, transport=relay)
    proxy = settings.gem_proxy_url.get_secret_value() if settings.gem_proxy_url else None
    return GemBidplusAdapter(config, limiter, proxy=proxy)
