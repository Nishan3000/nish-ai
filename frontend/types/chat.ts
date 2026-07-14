/**
 * Chat types — kept deliberately in sync with the backend Pydantic
 * schemas in `backend/app/schemas/chat.py`.
 */

export type Role = "user" | "assistant";

export interface ChatMessage {
  role: Role;
  content: string;
}

import type { MemoryUsed } from "@/types/memory";

export interface ChatResponse {
  reply: string;
  model: string;
  /** Long-term memories injected into this reply (may be empty). */
  memories_used: MemoryUsed[];
}

export interface HealthResponse {
  status: "ok";
  app: string;
  ollama: "reachable" | "unreachable";
  ollama_model: string;
}
