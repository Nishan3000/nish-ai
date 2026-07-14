/**
 * API client for the Nova AI backend.
 *
 * One place owns the base URL, JSON handling, and error normalization,
 * so components never touch `fetch` directly.
 */

import type { ChatMessage, ChatResponse, HealthResponse } from "@/types/chat";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Error carrying a human-readable message safe to show in the UI. */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(
      "Cannot reach the Nova backend. Is it running on " + API_URL + "?",
    );
  }

  if (!response.ok) {
    // FastAPI puts human-readable errors in `detail`.
    let detail = `Request failed (HTTP ${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body — keep the generic message.
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

/** Send the whole conversation; the backend is stateless in Phase 1. */
export function sendChat(messages: ChatMessage[]): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ messages }),
  });
}

/** Backend + Ollama status, shown in the header. */
export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}
