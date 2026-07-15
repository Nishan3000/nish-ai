/**
 * API client for the NISH backend.
 *
 * One place owns the base URL (from NEXT_PUBLIC_API_URL), JSON handling,
 * abort support, and error normalization — components never touch fetch.
 */

import type { AgentTask, AuditVerify, RepoTree } from "@/types/agent";
import type { IdentityInfo } from "@/types/identity";
import type { Memory, MemoryType } from "@/types/memory";
import type {
  CodingProject,
  CodingTask,
  ProjectScan,
} from "@/types/coding";
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
      `Cannot reach the NISH backend at ${API_URL}. Is it running?`,
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

/** Public application identity (name, creator, version, model). */
export function getIdentity(): Promise<IdentityInfo> {
  return request<IdentityInfo>("/api/identity");
}

/* --------------------------------------------------------- memories --- */

export function listMemories(params?: {
  memory_type?: MemoryType;
  q?: string;
}): Promise<Memory[]> {
  const search = new URLSearchParams();
  if (params?.memory_type) search.set("memory_type", params.memory_type);
  if (params?.q) search.set("q", params.q);
  const suffix = search.size > 0 ? `?${search.toString()}` : "";
  return request<Memory[]>(`/api/memories${suffix}`);
}

export function createMemory(body: {
  memory_type: MemoryType;
  content: string;
  importance_score?: number;
}): Promise<Memory> {
  return request<Memory>("/api/memories", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateMemory(
  id: string,
  body: Partial<{
    content: string;
    memory_type: MemoryType;
    importance_score: number;
    is_active: boolean;
  }>,
): Promise<Memory> {
  return request<Memory>(`/api/memories/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteMemory(id: string): Promise<void> {
  return request<void>(`/api/memories/${id}`, { method: "DELETE" });
}

export function clearAllMemories(): Promise<{ cleared: number }> {
  return request<{ cleared: number }>("/api/memories?confirm=true", {
    method: "DELETE",
  });
}

/* ----------------------------------------------------------- coding --- */

export function listCodingProjects(): Promise<CodingProject[]> {
  return request<CodingProject[]>("/api/coding/projects");
}

export function registerCodingProject(body: {
  name: string;
  root_path: string;
  description?: string;
}): Promise<CodingProject> {
  return request<CodingProject>("/api/coding/projects", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function scanCodingProject(id: string): Promise<ProjectScan> {
  return request<ProjectScan>(`/api/coding/projects/${id}/scan`, {
    method: "POST",
  });
}

export function createCodingTask(
  body: { project_id: string; description: string },
  signal?: AbortSignal,
): Promise<CodingTask> {
  return request<CodingTask>("/api/coding/tasks", {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
}

export function listCodingTasks(projectId?: string): Promise<CodingTask[]> {
  const suffix = projectId ? `?project_id=${projectId}` : "";
  return request<CodingTask[]>(`/api/coding/tasks${suffix}`);
}

export function getCodingTask(id: string): Promise<CodingTask> {
  return request<CodingTask>(`/api/coding/tasks/${id}`);
}

export function codingTaskStage(
  id: string,
  stage: "workspace" | "generate" | "review",
  signal?: AbortSignal,
): Promise<CodingTask> {
  return request<CodingTask>(`/api/coding/tasks/${id}/${stage}`, {
    method: "POST",
    signal,
  });
}

export function validateCodingTask(
  id: string,
  commands: string[],
  signal?: AbortSignal,
): Promise<CodingTask> {
  return request<CodingTask>(`/api/coding/tasks/${id}/validate`, {
    method: "POST",
    body: JSON.stringify({ commands }),
    signal,
  });
}

export function decideCodingTask(
  id: string,
  decision: "approved" | "rejected",
  note = "",
): Promise<{ decision: string; message: string }> {
  return request<{ decision: string; message: string }>(
    `/api/coding/tasks/${id}/decision`,
    { method: "POST", body: JSON.stringify({ decision, note }) },
  );
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
