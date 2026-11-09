"""Health and readiness endpoints."""

from fastapi import APIRouter, Request, Response, status

from app.core.config import Settings
from app.db.database import Database
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
def liveness(request: Request) -> HealthResponse:
    """Report process liveness without touching external dependencies."""

    settings: Settings = request.app.state.settings
    return HealthResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
def readiness(request: Request, response: Response) -> ReadinessResponse:
    """Report readiness, including database connectivity."""

    settings: Settings = request.app.state.settings
    database: Database = request.app.state.database
    connected = database.check_connection()

    if not connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ok" if connected else "degraded",
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        database="connected" if connected else "unavailable",
    )
