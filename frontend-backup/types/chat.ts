/**
 * Chat types — kept deliberately in sync with the backend Pydantic
 * schemas in `backend/app/schemas/chat.py`.
 */

export type Role = "user" | "assistant";

export interface ChatMessage {
  role: Role;
  content: string;
}

export interface ChatResponse {
  reply: string;
  model: string;
}

export interface HealthResponse {
  status: "ok";
  app: string;
  ollama: "reachable" | "unreachable";
  ollama_model: string;
}
