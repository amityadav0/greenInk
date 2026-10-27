"""Price intel: Lightning picks unit prices from Tavily results; code computes the band."""

import asyncio
import json
from typing import Any
from uuid import uuid4

from pydantic import SecretStr

from greenink.core.enums import LLMTask
from greenink.intel.tavily import TavilyIntelProvider, band, item_name
from greenink.llm.port import LLMInput
from tests.fakes import FakeLLM


def test_band_drops_lot_prices_and_tender_values() -> None:
    # Unit prices around 20k, one lot price and one whole-tender value.
    assert band([18_000, 21_000, 19_500, 23_000, 1_355_000, 19_300_000]) == (18_375.0, 22_500.0)
    assert band([42_000]) == (42_000, 42_000)
    assert band([19_000, 115_000]) == (19_000, 115_000), "two prices: both kept"
    assert band([]) == (None, None)
    assert band([3.0]) == (None, None), "below the plausible range"


def test_item_name() -> None:
    assert item_name("11kV CT 1200/5 (BoQ for substations)") == "11kV CT 1200/5"


class FakeTavily:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = results
        self.queries: list[str] = []

    async def search(self, query: str, **_: Any) -> dict[str, Any]:
        self.queries.append(query)
        return {"results": self.results}


def test_prices_cites_every_source_and_uses_lightning_unit_prices() -> None:
    results = [
        {"url": "https://a.example/ct", "title": "11kV CT price", "content": "Rs. 21,000 per piece"},
        {"url": "https://b.example/tender", "title": "Tender worth Rs 1.93 crore", "content": "..."},
        {"url": "https://c.example/blog", "title": "What is a CT", "content": "No prices here"},
    ]

    def price(sent: LLMInput) -> dict[str, Any]:
        candidates = json.loads(sent.data["results"])
        assert [c["index"] for c in candidates] == [0, 1], "only results with a rupee amount are sent"
        return {"prices": [{"index": 0, "unit_price_inr": 21000}, {"index": 1, "unit_price_inr": None}]}

    llm = FakeLLM(price_intel=price)
    provider = TavilyIntelProvider(SecretStr("k"), llm)
    fake = FakeTavily(results)
    provider._client = fake
    analysis_id = uuid4()
    intel = asyncio.run(provider.prices(analysis_id, "11kV Current Transformer (BHEL)", "Example Dept"))

    assert fake.queries == [
        "11kV Current Transformer price per unit India",
        "Example Dept 11kV Current Transformer purchase order rate",
    ]
    assert [str(s.url) for s in intel.sources] == [r["url"] for r in results], "duplicates removed, all cited"
    assert [s.price_inr for s in intel.sources] == [21000, None, None]
    assert (intel.band_low, intel.band_high) == (21000, 21000)
    [(task, _, sent_analysis)] = llm.calls
    assert task == LLMTask.PRICE_INTEL
    assert sent_analysis == analysis_id
