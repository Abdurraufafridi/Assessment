"""Health-check response schemas."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness response: the process is running and serving requests."""

    status: Literal["ok"] = "ok"
    name: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    """Readiness response: dependencies required to serve traffic are healthy."""

    status: Literal["ok", "degraded"]
    name: str
    version: str
    environment: str
    database: Literal["connected", "unavailable"]
