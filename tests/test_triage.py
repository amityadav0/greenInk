"""Triage: the model's green badges are checked against the company's product list."""

import asyncio
import json
from typing import Any
from uuid import uuid4

from greenink.core.enums import TenderSource, TriageLevel
from greenink.core.models import BidSummary, CompanyProfile, TriageBadge
from greenink.llm.port import LLMInput
from greenink.triage.score import LLMTriage, check_badge, on_product_list, product_keys
from tests.conftest import REPO_ROOT
from tests.fakes import FakeLLM

BRIGHTLINE = json.loads((REPO_ROOT / "seed" / "brightline" / "profile.json").read_text())["products"]
KEYS = product_keys(BRIGHTLINE)
GREEN = TriageBadge(level=TriageLevel.GREEN, reason="Makes CTs.")


def test_product_keys_drop_ratings_and_details() -> None:
    assert frozenset({"current", "transformer"}) in KEYS
    assert frozenset({"potential", "transformer"}) in KEYS


def test_real_product_bids_stay_green() -> None:
    for title in [
        "E4963063 11KV and 33KV Outdoor CT 01-SG4960097000-11 KV CT RATIO CURRENT TRANSFORMER",
        "Supply of 245 KV Current Transformer for various Substations",
        "66 kV Potential Transformer for Sub-stations / Power Houses (PSPCL)",
    ]:
        assert on_product_list(title, KEYS), title
        assert check_badge(GREEN, title, KEYS) == GREEN


def test_lookalikes_become_amber() -> None:
    for title in [
        "RELAY CURRENT SENSATIVE",
        "PR_ 100279470_ INSULATOR, POLYMERIC PIN, 11KV, OH LINE",
        "Primary Current Injection Kit",
        "Calibration Services - Electrical; Voltage, Current, Power",
    ]:
        checked = check_badge(GREEN, title, KEYS)
        assert checked.level == TriageLevel.AMBER, title
        assert checked.reason.startswith("Not on your product list.")


def test_red_for_a_listed_product_becomes_amber() -> None:
    red = TriageBadge(level=TriageLevel.RED, reason="245 kV CT; company makes up to 11 kV only")
    checked = check_badge(red, "Supply of 245 KV Current Transformer for various Substations", KEYS)
    assert checked.level == TriageLevel.AMBER
    assert checked.reason.startswith("Your product type, but:")


def test_other_badges_are_left_alone_and_no_products_means_no_check() -> None:
    red = TriageBadge(level=TriageLevel.RED, reason="Not our product.")
    amber = TriageBadge(level=TriageLevel.AMBER, reason="Close variant.")
    assert check_badge(red, "RELAY", KEYS) == red
    assert check_badge(amber, "Current Transformer", KEYS) == amber
    assert check_badge(GREEN, "RELAY", []) == GREEN


def _bid(ref: str, title: str) -> BidSummary:
    return BidSummary(tender_id=uuid4(), source=TenderSource.GEM, source_ref=ref, title=title)


def test_badges_map_back_by_local_ref_and_skipped_bids_are_rescored() -> None:
    bids = [
        _bid("GEM/2026/B/8211793", "11 kV Current Transformer"),
        _bid("GEM/2026/B/8211794", "HRC Fuse Link"),
        _bid("GEM/2026/B/8211795", "Office Chair"),
    ]

    def answer(input: LLMInput) -> dict[str, Any]:
        listed = json.loads(input.data["bids"])
        # The first pass skips the last bid; the rescore sees only that one.
        shown = listed[:-1] if len(listed) == 3 else listed
        return {
            "scores": [
                {"source_ref": b["source_ref"], "badge": {"level": "red", "reason": f"About {b['title']}"}}
                for b in shown
            ]
        }

    llm = FakeLLM(triage=answer)
    badges = asyncio.run(LLMTriage(llm).score(bids, CompanyProfile(legal_name="Brightline Electricals")))

    assert {ref: badge.reason for ref, badge in badges.items()} == {
        "GEM/2026/B/8211793": "About 11 kV Current Transformer",
        "GEM/2026/B/8211794": "About HRC Fuse Link",
        "GEM/2026/B/8211795": "About Office Chair",
    }
    assert len(llm.calls) == 2
    assert [b["source_ref"] for b in json.loads(llm.calls[0][1].data["bids"])] == ["bid-1", "bid-2", "bid-3"]
