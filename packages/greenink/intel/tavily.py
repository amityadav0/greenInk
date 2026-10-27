"""Price intel from Tavily Search, called at runtime. The band is computed by code from the
rupee amounts in the results, and every source is cited in the price panel."""

import re
import statistics
from typing import Any
from uuid import UUID

import structlog
from pydantic import SecretStr
from tavily import AsyncTavilyClient

from greenink.core.enums import ErrorCode
from greenink.core.errors import GreenInkError
from greenink.core.models import PriceIntel, PriceSource

log = structlog.get_logger()

MAX_RESULTS = 6
_AMOUNT = re.compile(
    r"(?:₹|\brs\.?|\binr)\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(lakhs?|lacs?|crores?|cr\b|k\b)?", re.IGNORECASE
)
_SCALE = {
    "lakh": 1e5,
    "lakhs": 1e5,
    "lac": 1e5,
    "lacs": 1e5,
    "crore": 1e7,
    "crores": 1e7,
    "cr": 1e7,
    "k": 1e3,
}
PLAUSIBLE = (10.0, 5e7)
"""Unit prices outside this range are noise (phone numbers, tender values, page counts)."""


def amounts(text: str) -> list[float]:
    found = []
    for number, unit in _AMOUNT.findall(text):
        try:
            value = float(number.replace(",", "")) * _SCALE.get((unit or "").lower(), 1.0)
        except ValueError:
            continue
        if PLAUSIBLE[0] <= value <= PLAUSIBLE[1]:
            found.append(value)
    return found


def band(prices: list[float]) -> tuple[float | None, float | None]:
    """Middle half of the observed prices; with fewer than four, their min and max."""
    if not prices:
        return None, None
    ordered = sorted(prices)
    if len(ordered) < 4:
        return ordered[0], ordered[-1]
    quartiles = statistics.quantiles(ordered, n=4)
    return round(quartiles[0], 2), round(quartiles[2], 2)


def item_name(title: str) -> str:
    """'11kV CT 1200/5 (BoQ for substations)' -> '11kV CT 1200/5', at most 80 characters."""
    return title.split("(")[0].strip()[:80] or title[:80]


class TavilyIntelProvider:
    def __init__(self, api_key: SecretStr) -> None:
        self._client = AsyncTavilyClient(api_key=api_key.get_secret_value())

    async def _search(self, query: str) -> list[dict[str, Any]]:
        try:
            response = await self._client.search(
                query, max_results=MAX_RESULTS, search_depth="basic", country="india"
            )
        except Exception as exc:
            raise GreenInkError(
                ErrorCode.UPSTREAM_UNAVAILABLE, "Price search is unavailable right now."
            ) from exc
        results: list[dict[str, Any]] = response.get("results", [])
        return results

    async def prices(self, analysis_id: UUID, item: str, buyer: str | None) -> PriceIntel:
        name = item_name(item)
        results = await self._search(f"{name} price per unit India")
        if buyer:
            results += await self._search(f"{buyer} {name} purchase order rate")
        sources: list[PriceSource] = []
        observed: list[float] = []
        seen: set[str] = set()
        for result in results:
            url = result.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            found = amounts(f"{result.get('title', '')} {result.get('content', '')}")
            observed.extend(found)
            sources.append(
                PriceSource(
                    title=str(result.get("title") or url)[:200],
                    url=url,
                    snippet=str(result.get("content") or "")[:300] or None,
                    price_inr=statistics.median(found) if found else None,
                    provider="tavily",
                )
            )
        low, high = band(observed)
        log.info("price_intel", item=name, sources=len(sources), prices=len(observed))
        return PriceIntel(analysis_id=analysis_id, item=name, band_low=low, band_high=high, sources=sources)
