"""Health check endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str


@router.get("/", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Basic health check endpoint.
    
    Returns:
        Health status and version
    """
    return HealthResponse(status="healthy", version="0.1.0")


@router.get("/ready", response_model=HealthResponse)
async def readiness_check() -> HealthResponse:
    """Readiness check with dependency validation.
    
    Returns:
        Readiness status
    """
    # TODO: Check database, cache, external APIs
    return HealthResponse(status="ready", version="0.1.0")


@router.get("/live", response_model=HealthResponse)
async def liveness_check() -> HealthResponse:
    """Liveness check for orchestration.
    
    Returns:
        Liveness status
    """
    return HealthResponse(status="alive", version="0.1.0")
