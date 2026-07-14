/**
 * Local conversation persistence.
 *
 * Conversations live in the browser's localStorage until the PostgreSQL
 * phase moves them server-side. All access goes through these helpers so
 * the storage backend can be swapped without touching components.
 */

import type { Conversation, StoredMessage } from "@/types/conversation";

// Legacy key name kept on purpose: renaming it would silently delete
// existing users' saved conversations.
const STORAGE_KEY = "nova.conversations.v1";
const MAX_CONVERSATIONS = 100;

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

export function loadConversations(): Conversation[] {
  if (!isBrowser()) return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Conversation[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    // Corrupt storage: start fresh rather than crash the app.
    return [];
  }
}

export function saveConversations(conversations: Conversation[]): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(conversations.slice(0, MAX_CONVERSATIONS)),
    );
  } catch {
    // Storage full or blocked — the app still works, just without history.
  }
}

export function newConversation(): Conversation {
  const now = Date.now();
  return {
    id: `c_${now.toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
    title: "New chat",
    messages: [],
    createdAt: now,
    updatedAt: now,
  };
}

/** Derive a title from the first user message. */
export function titleFor(messages: StoredMessage[]): string {
  const first = messages.find((message) => message.role === "user");
  if (!first) return "New chat";
  const clean = first.content.replace(/\s+/g, " ").trim();
  return clean.length > 42 ? `${clean.slice(0, 42)}…` : clean;
}
