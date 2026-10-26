"""The frozen contracts: committed files match the code, and enums match SPEC."""

import re

from greenink.core import enums
from greenink.core.schemas import render_schemas
from greenink_api.contract import render_openapi
from greenink_api.main import create_app
from tests.conftest import REPO_ROOT

CONTRACTS = REPO_ROOT / "contracts"
SPEC = (REPO_ROOT / "docs" / "SPEC.md").read_text(encoding="utf-8")


def test_openapi_yaml_matches_the_app() -> None:
    committed = (CONTRACTS / "openapi.yaml").read_text(encoding="utf-8")
    assert committed == render_openapi(), "contracts/openapi.yaml is stale: run `make openapi`"


def test_json_schemas_match_the_models() -> None:
    expected = render_schemas()
    committed = {p.name: p.read_text(encoding="utf-8") for p in (CONTRACTS / "schemas").glob("*.json")}
    assert committed == expected, "contracts/schemas/ is stale: run `make openapi`"


def test_every_spec_route_is_in_the_contract() -> None:
    table = SPEC.split("## API contract", 1)[1].split("## LLM gateway", 1)[0]
    spec_routes: set[tuple[str, str]] = set()
    for method, cell in re.findall(r"^\| (GET|POST) \| (.+?) \|", table, flags=re.MULTILINE):
        for raw in re.findall(r"`([^`]+)`", cell):
            path = raw.split("?", 1)[0]
            spec_routes.add((method.lower(), re.sub(r"\{[^}]+\}", "{}", path)))
    paths = create_app().openapi()["paths"]
    contract_routes = {
        (method, re.sub(r"\{[^}]+\}", "{}", path)) for path, ops in paths.items() for method in ops
    }
    assert len(spec_routes) == 17
    assert spec_routes == contract_routes


def _spec_enum(label: str) -> set[str]:
    line = next(line for line in SPEC.splitlines() if line.startswith(f"- {label}"))
    return set(re.findall(r"`([a-z_]+)`", line.split(":", 1)[1].split(". Severity")[0]))


def test_enums_match_spec() -> None:
    assert {c.value for c in enums.RequirementCategory} == _spec_enum("Requirement category")
    assert {s.value for s in enums.FindingStatus} == _spec_enum("Finding status")
    assert {s.value for s in enums.Severity} == {"critical", "high", "medium", "low"}
    assert {v.value for v in enums.Verdict} == _spec_enum("Verdict")
    assert {s.value for s in enums.AnalysisStatus} == _spec_enum("Analysis status")
    assert {m.value for m in enums.PageMethod} == {"text", "vision"}
    assert {s.value for s in enums.CompanySource} == {"demo", "docs", "url"}


def test_no_raw_validation_error_schema_in_openapi() -> None:
    schemas = create_app().openapi()["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
