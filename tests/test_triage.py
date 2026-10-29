"""Triage: the model's green badges are checked against the company's product list."""

import json

from greenink.core.enums import TriageLevel
from greenink.core.models import TriageBadge
from greenink.triage.score import check_green, on_product_list, product_keys
from tests.conftest import REPO_ROOT

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
        assert check_green(GREEN, title, KEYS) == GREEN


def test_lookalikes_become_amber() -> None:
    for title in [
        "RELAY CURRENT SENSATIVE",
        "PR_ 100279470_ INSULATOR, POLYMERIC PIN, 11KV, OH LINE",
        "Primary Current Injection Kit",
        "Calibration Services - Electrical; Voltage, Current, Power",
    ]:
        checked = check_green(GREEN, title, KEYS)
        assert checked.level == TriageLevel.AMBER, title
        assert checked.reason.startswith("Not on your product list.")


def test_amber_and_red_are_left_alone_and_no_products_means_no_check() -> None:
    red = TriageBadge(level=TriageLevel.RED, reason="Not our product.")
    assert check_green(red, "RELAY", KEYS) == red
    assert check_green(GREEN, "RELAY", []) == GREEN
