"""FastAPI app: `/v1` routes, health checks, one error shape."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from greenink.core.logging import configure_logging
from greenink.core.settings import Settings, get_settings
from greenink_api.deps import AppState, build_state
from greenink_api.errors import install_error_handlers
from greenink_api.routes import analyses, companies, health, search, tenders

API_VERSION = "0.1.0"


def create_app(
    settings: Settings | None = None,
    state_factory: Callable[[Settings], Awaitable[AppState]] = build_state,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        services = await state_factory(settings)
        app.state.settings = settings
        app.state.services = services
        app.state.engine = services.engine
        try:
            yield
        finally:
            await services.aclose()

    app = FastAPI(
        title="Green Ink API",
        version=API_VERSION,
        summary="Government tenders a small manufacturer can win, and the clauses that would reject the bid.",
        license_info={"name": "MIT", "identifier": "MIT"},
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )
    install_error_handlers(app)
    for module in (health, search, tenders, companies, analyses):
        app.include_router(module.router)
    return app


configure_logging(get_settings().log_level, json=get_settings().env != "local")
app = create_app()
