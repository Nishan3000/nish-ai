"""Health endpoint.

Reports both the API's own liveness and whether Ollama is reachable, so
"the backend is up but the model server is down" is diagnosable from one
request.
"""

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.chat import HealthResponse
from app.services.ollama import OllamaService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness + Ollama reachability check."""
    ollama = OllamaService(settings)
    reachable = await ollama.is_reachable()
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        ollama="reachable" if reachable else "unreachable",
        ollama_model=settings.ollama_model,
    )
