/** A locally stored conversation (browser localStorage; DB in Phase 2). */

import type { ChatMessage } from "@/types/chat";

import type { MemoryUsed } from "@/types/memory";

export interface StoredMessage extends ChatMessage {
  /** Unix ms — used for "only when useful" timestamps. */
  at: number;
  /** Long-term memories NISH used to produce this reply (assistant only). */
  memoriesUsed?: MemoryUsed[];
}

export interface Conversation {
  id: string;
  title: string;
  messages: StoredMessage[];
  createdAt: number;
  updatedAt: number;
}
