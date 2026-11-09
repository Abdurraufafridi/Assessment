"""FastAPI application factory and ASGI entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.db.database import Database

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an application instance.

    Accepting settings as an argument keeps tests isolated from the process-wide
    configuration while production uses the cached environment settings.
    """

    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(resolved_settings.database_url)
        if resolved_settings.app_env != "production":
            database.create_all()
        app.state.database = database
        logger.info(
            "application_started",
            extra={
                "environment": resolved_settings.app_env,
                "version": resolved_settings.app_version,
            },
        )
        try:
            yield
        finally:
            database.dispose()
            logger.info("application_stopped")

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        debug=resolved_settings.debug,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.include_router(health.router)
    return application


app = create_app()
