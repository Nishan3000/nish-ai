/** A locally stored conversation (browser localStorage; DB in Phase 2). */

import type { ChatMessage } from "@/types/chat";

export interface StoredMessage extends ChatMessage {
  /** Unix ms — used for "only when useful" timestamps. */
  at: number;
}

export interface Conversation {
  id: string;
  title: string;
  messages: StoredMessage[];
  createdAt: number;
  updatedAt: number;
}
