"""API skeleton: health checks, the error shape, and a 501 for every route not built yet."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from greenink.core.api import ErrorBody
from greenink_api.routes import health


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


def test_unbuilt_export_returns_501_with_error_shape(client: TestClient) -> None:
    response = client.get(f"/v1/analyses/{uuid4()}/export.pdf")
    assert response.status_code == 501
    assert_error_shape(response.json(), "not_implemented")
    assert response.json()["retryable"] is False


def test_routes_fail_cleanly_when_the_database_is_down(client: TestClient) -> None:
    response = client.get(f"/v1/tenders/{uuid4()}")
    assert response.status_code == 500
    assert_error_shape(response.json(), "internal")


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
