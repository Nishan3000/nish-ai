/**
 * API client for the Nova AI backend.
 *
 * One place owns the base URL (from NEXT_PUBLIC_API_URL), JSON handling,
 * abort support, and error normalization — components never touch fetch.
 */

import type { AgentTask, AuditVerify, RepoTree } from "@/types/agent";
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

/** Thrown when the caller aborted the request (e.g. Stop button). */
export class AbortedError extends Error {
  constructor() {
    super("Request stopped.");
    this.name = "AbortedError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new AbortedError();
    }
    throw new ApiError(
      `Cannot reach the Nova backend at ${API_URL}. Is it running?`,
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

export function apiBaseUrl(): string {
  return API_URL;
}

/* ------------------------------------------------------------- chat --- */

/** Send the whole conversation; the backend is stateless for chat. */
export function sendChat(
  messages: ChatMessage[],
  signal?: AbortSignal,
): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ messages }),
    signal,
  });
}

/** Backend + Ollama status. */
export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

/* ------------------------------------------------------------ agent --- */

/** Create an agent task; the backend plans it before responding. */
export function createAgentTask(
  description: string,
  signal?: AbortSignal,
): Promise<AgentTask> {
  return request<AgentTask>("/api/agent/tasks", {
    method: "POST",
    body: JSON.stringify({ description }),
    signal,
  });
}

export function listAgentTasks(): Promise<{ tasks: AgentTask[] }> {
  return request<{ tasks: AgentTask[] }>("/api/agent/tasks");
}

export function getRepoTree(): Promise<RepoTree> {
  return request<RepoTree>("/api/agent/repo/tree");
}

export function verifyAudit(): Promise<AuditVerify> {
  return request<AuditVerify>("/api/agent/audit/verify");
}
