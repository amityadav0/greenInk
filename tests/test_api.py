"""API skeleton: health checks, the error shape, and a 501 for every route not built yet."""

import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from greenink.core.api import ErrorBody
from greenink_api.routes import health

VALID_BODIES = {
    "createCompany": {"name": "Brightline Electricals", "profile": {"legal_name": "Brightline Electricals"}},
    "createCompanyFromUrl": {"url": "https://example.com"},
    "createAnalysis": {"tender_id": str(uuid4()), "company_id": str(uuid4())},
}
QUERIES = {"search": {"q": "current transformer"}}


def contract_operations(client: TestClient) -> list[tuple[str, str, str]]:
    """(method, path, operationId) for every /v1 operation in the app's OpenAPI document."""
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    return [
        (method, path, op["operationId"])
        for path, ops in paths.items()
        if path.startswith("/v1/")
        for method, op in ops.items()
    ]


def assert_error_shape(body: object, code: str) -> None:
    error = ErrorBody.model_validate(body)
    assert error.code == code
    assert error.message


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_ok_when_dependencies_answer(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def ok(*_: object) -> bool:
        return True

    monkeypatch.setattr(health, "_check_postgres", ok)
    monkeypatch.setattr(health, "_check_redis", ok)
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"postgres": True, "redis": True}}


def test_readyz_503_with_error_shape_when_dependencies_are_down(client: TestClient) -> None:
    response = client.get("/readyz")  # the fixture points at closed ports
    assert response.status_code == 503
    assert_error_shape(response.json(), "not_ready")
    assert response.json()["retryable"] is True
    assert "postgres" in response.json()["message"]


def test_every_contract_route_returns_501_with_error_shape(client: TestClient) -> None:
    operations = contract_operations(client)
    assert len(operations) == 15
    for method, template, operation_id in operations:
        path = re.sub(r"\{page_no\}", "1", template)
        path = re.sub(r"\{[a-z_]+\}", str(uuid4()), path)
        response = client.request(
            method, path, params=QUERIES.get(operation_id), json=VALID_BODIES.get(operation_id)
        )
        assert response.status_code == 501, (method, template, response.text)
        assert_error_shape(response.json(), "not_implemented")
        assert response.json()["retryable"] is False


def test_validation_errors_use_error_shape(client: TestClient) -> None:
    response = client.get("/v1/tenders/not-a-uuid")
    assert response.status_code == 422
    assert_error_shape(response.json(), "validation_error")


def test_unknown_route_uses_error_shape(client: TestClient) -> None:
    response = client.get("/v1/nope")
    assert response.status_code == 404
    assert_error_shape(response.json(), "not_found")


def test_unhandled_errors_become_500_without_leaking_details() -> None:
    from greenink.core.settings import Settings
    from greenink_api.main import create_app

    app = create_app(Settings(database_url="postgresql+psycopg://x:x@127.0.0.1:1/x"))

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("database password is hunter2")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/boom")
    assert response.status_code == 500
    assert_error_shape(response.json(), "internal")
    assert "hunter2" not in response.text
    assert response.json()["retryable"] is True


def test_wrong_method_uses_error_shape(client: TestClient) -> None:
    response = client.post("/healthz")
    assert response.status_code == 405
    assert_error_shape(response.json(), "bad_request")


def test_sse_routes_return_501_not_an_empty_stream(client: TestClient) -> None:
    response = client.get(f"/v1/analyses/{uuid4()}/events")
    assert response.status_code == 501
    assert response.headers["content-type"].startswith("application/json")
