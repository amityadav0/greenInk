"""GeM spike parsing and HTTP behaviour, against synthetic fixtures (no network, no real bids)."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

from tests.conftest import REPO_ROOT


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gem_spike", REPO_ROOT / "scripts" / "gem_spike.py")
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gem = _load()

# Shaped like a bidplus `all-bids-data` doc; every value is invented.
DOC: dict[str, Any] = {
    "b_id": [1234567],
    "b_bid_number": ["GEM/2026/B/0000001"],
    "b_category_name": ["11kV Current Transformer"],
    "bbt_title": ["Example Buyer CT"],
    "ba_official_details_minName": ["Ministry of Examples"],
    "ba_official_details_deptName": ["Department of Samples"],
    "b_total_quantity": [6],
    "final_end_date_sort": ["2026-11-06T12:00:00Z"],
    "b_bid_type": [1],
}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(gem.time, "sleep", slept.append)
    return slept


def test_parse_csrf() -> None:
    html = "data: {'payload': x, 'csrf_bd_gem_nk': '5cb5add4c35dc2bbf913ad774a2084dd'},"
    assert gem.parse_csrf(html) == "5cb5add4c35dc2bbf913ad774a2084dd"
    with pytest.raises(RuntimeError, match="csrf token not found"):
        gem.parse_csrf("<html>changed layout</html>")


def test_search_payload_shape() -> None:
    payload = gem.search_payload("current transformer", 2, sort="Bid-Start-Date-Latest")
    assert payload["page"] == 2
    assert payload["param"] == {"searchBid": "current transformer", "searchType": "fullText"}
    assert payload["filter"]["bidStatusType"] == "ongoing_bids"
    assert payload["filter"]["sort"] == "Bid-Start-Date-Latest"


def test_parse_search_ok_and_error() -> None:
    body = {"code": 200, "response": {"response": {"numFound": "41", "docs": [DOC]}}}
    assert gem.parse_search(body) == (41, [DOC])
    with pytest.raises(RuntimeError, match="answered code 500"):
        gem.parse_search({"code": 500, "message": "error"})


def test_to_bid_regular_bid() -> None:
    bid = gem.to_bid(DOC)
    assert bid.bid_number == "GEM/2026/B/0000001"
    assert bid.title == "11kV Current Transformer (Example Buyer CT)"
    assert bid.buyer == "Ministry of Examples, Department of Samples"
    assert bid.quantity == 6
    assert bid.end_date == "2026-11-06 12:00 IST"
    assert bid.document_url == "https://bidplus.gem.gov.in/showbidDocument/1234567"


@pytest.mark.parametrize(
    ("bid_type", "path"), [(2, "showradocumentPdf"), (5, "showdirectradocumentPdf"), (1, "showbidDocument")]
)
def test_to_bid_document_path_by_bid_type(bid_type: int, path: str) -> None:
    assert gem.to_bid({**DOC, "b_bid_type": [bid_type]}).document_url.endswith(f"/{path}/1234567")


def test_to_bid_tolerates_missing_fields() -> None:
    bid = gem.to_bid({"b_id": 9, "b_bid_number": "GEM/2026/B/9"})
    assert bid.title == ""
    assert bid.buyer == ""
    assert bid.quantity is None
    assert bid.end_date == ""


def test_title_matches_ignores_case_and_spacing() -> None:
    bid = gem.to_bid({**DOC, "b_category_name": ["11kV  CURRENT\nTransformer"], "bbt_title": None})
    assert gem.title_matches(bid, "current transformer")
    assert not gem.title_matches(bid, "energy meter")


def _client(handler: Any) -> Any:
    return gem.PoliteClient(transport=httpx.MockTransport(handler))


def test_client_retries_5xx_then_succeeds(no_sleep: list[float]) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(503 if len(calls) < 3 else 200, text="ok")

    response = _client(handler).request("GET", "/all-bids")
    assert response.status_code == 200
    assert len(calls) == 3
    assert any(wait > 1.5 for wait in no_sleep), "backoff should grow between retries"


def test_client_does_not_retry_404() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(404)

    assert _client(handler).request("POST", "/all-bids-data").status_code == 404
    assert len(calls) == 1


def test_client_gives_up_on_repeated_network_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(httpx.ConnectError):
        _client(handler).request("GET", "/all-bids")


def test_client_sends_project_user_agent() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["user-agent"])
        return httpx.Response(200)

    _client(handler).request("GET", "/all-bids")
    assert seen == [gem.USER_AGENT]
    assert "GreenInk" in gem.USER_AGENT


@pytest.mark.parametrize(
    ("status", "content", "expected"),
    [
        (200, b"%PDF-1.7 fake", "saved"),
        (200, b"<html>login</html>", "not a PDF"),
        (404, b"", "HTTP 404"),
    ],
)
def test_download_outcomes(tmp_path: Path, status: int, content: bytes, expected: str) -> None:
    client = _client(lambda request: httpx.Response(status, content=content))
    outcome = gem.download(client, gem.to_bid(DOC), tmp_path)
    assert outcome.startswith(expected)
    saved = list(tmp_path.glob("*.pdf"))
    assert [p.name for p in saved] == (["GEM-2026-B-0000001.pdf"] if expected == "saved" else [])


def test_index_is_json_serialisable() -> None:
    from dataclasses import asdict

    assert json.loads(json.dumps(asdict(gem.to_bid(DOC))))["bid_number"] == "GEM/2026/B/0000001"
