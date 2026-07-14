"""Service layer for talking to a local Ollama server.

Why a dedicated service class instead of calling httpx from the route?
  * The API layer stays thin and testable.
  * In later phases we add more model providers behind the same interface,
    so the "model router" can swap providers without touching routes.
  * All Ollama-specific error handling lives in one place.
"""

import logging
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)

# System prompt is defined server-side and prepended to every request.
# Clients can only send "user"/"assistant" roles (enforced by the schema),
# so this cannot be overridden from the outside.
SYSTEM_PROMPT = (
    "You are NISH, a helpful personal AI assistant. "
    "Be accurate, concise, and honest. If you are unsure, say so."
)


class OllamaError(Exception):
    """Base error for Ollama failures. Carries an HTTP-friendly message."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class OllamaUnavailableError(OllamaError):
    """Raised when the Ollama server cannot be reached at all."""

    def __init__(self, base_url: str) -> None:
        super().__init__(
            f"Cannot reach Ollama at {base_url}. "
            "Is Ollama running? Start it with `ollama serve` "
            "(or open the Ollama app).",
            status_code=503,
        )


class OllamaService:
    """Thin async wrapper around the Ollama HTTP API."""

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model
        self._timeout = settings.ollama_timeout_seconds

    @property
    def model(self) -> str:
        return self._model

    async def is_reachable(self) -> bool:
        """Return True if the Ollama server answers at all.

        Used by the health endpoint. Short timeout on purpose: a health
        check must never hang.
        """
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
    ) -> str:
        """Send a conversation to Ollama and return the assistant's reply.

        Args:
            messages: list of {"role": ..., "content": ...} dicts,
                already validated by the API layer. The server-side
                system prompt is prepended here.
            system_prompt: optional override. Used by internal agents
                (e.g. the planner); the public chat endpoint never sets
                this, so users still cannot influence the system prompt.

        Returns:
            The assistant's reply text.

        Raises:
            OllamaUnavailableError: server not reachable.
            OllamaError: server reachable but returned an error
                (e.g. model not pulled yet).
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
                *messages,
            ],
            "stream": False,  # Phase 1: simple request/response. Streaming later.
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/api/chat", json=payload
                )
        except httpx.ConnectError as exc:
            logger.error("Ollama connection failed: %s", exc)
            raise OllamaUnavailableError(self._base_url) from exc
        except httpx.TimeoutException as exc:
            logger.error("Ollama request timed out after %ss", self._timeout)
            raise OllamaError(
                f"Ollama did not respond within {self._timeout:.0f}s. "
                "The model may still be loading, or the machine is under "
                "heavy load. Try again, or use a smaller model.",
                status_code=504,
            ) from exc

        if response.status_code == 404:
            # Most common cause: the model has not been pulled.
            raise OllamaError(
                f"Ollama could not find model '{self._model}'. "
                f"Pull it first with: ollama pull {self._model}",
                status_code=502,
            )
        if response.status_code != 200:
            detail = _safe_error_detail(response)
            logger.error("Ollama returned %s: %s", response.status_code, detail)
            raise OllamaError(f"Ollama error: {detail}", status_code=502)

        data = response.json()
        reply = data.get("message", {}).get("content")
        if not isinstance(reply, str) or not reply:
            logger.error("Unexpected Ollama response shape: %r", data)
            raise OllamaError("Ollama returned an empty or malformed response.")
        return reply


def _safe_error_detail(response: httpx.Response) -> str:
    """Extract an error message from an Ollama response without crashing."""
    try:
        body = response.json()
        if isinstance(body, dict) and "error" in body:
            return str(body["error"])
    except ValueError:
        pass
    return f"HTTP {response.status_code}"
