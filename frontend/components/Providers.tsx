"use client";

/**
 * Application-wide client state, kept in three small contexts:
 *
 *  PreferencesContext  — theme (light/dark) + message density, persisted
 *                        to localStorage and applied to <html>.
 *  ConnectionContext   — backend/Ollama health, polled every 30s.
 *  ConversationsContext— locally stored chats shared by the sidebar and
 *                        the chat page.
 *
 * Kept in one file because they are tiny and always used together.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { getHealth } from "@/lib/api";
import {
  loadConversations,
  newConversation,
  saveConversations,
  titleFor,
} from "@/lib/conversations";
import type { HealthResponse } from "@/types/chat";
import type { Conversation, StoredMessage } from "@/types/conversation";

/* ------------------------------------------------------- preferences --- */

export type Theme = "light" | "dark";
export type Density = "comfortable" | "compact";

interface Preferences {
  theme: Theme;
  density: Density;
  setTheme: (theme: Theme) => void;
  setDensity: (density: Density) => void;
}

const PreferencesContext = createContext<Preferences | null>(null);

function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

function applyDensity(density: Density): void {
  document.documentElement.dataset.density = density;
}

/* -------------------------------------------------------- connection --- */

export interface Connection {
  health: HealthResponse | null; // null = backend unreachable
  checking: boolean;
  refresh: () => void;
}

const ConnectionContext = createContext<Connection | null>(null);

/* ----------------------------------------------------- conversations --- */

interface ConversationsApi {
  conversations: Conversation[];
  activeId: string | null;
  active: Conversation | null;
  select: (id: string) => void;
  startNew: () => void;
  /** Return the active conversation id, creating one if necessary. */
  ensureActive: () => string;
  setMessages: (id: string, messages: StoredMessage[]) => void;
  remove: (id: string) => void;
  clearAll: () => void;
}

const ConversationsContext = createContext<ConversationsApi | null>(null);

/* ----------------------------------------------------------- provider --- */

export function Providers({ children }: { children: React.ReactNode }) {
  // Preferences. Initial values are read by the no-flash script in
  // layout.tsx before hydration; here we just mirror them into state.
  const [theme, setThemeState] = useState<Theme>("dark");
  const [density, setDensityState] = useState<Density>("comfortable");

  // The "nova.*" localStorage keys are legacy names kept on purpose so
  // existing users' preferences survive the rebrand.
  useEffect(() => {
    const storedTheme = window.localStorage.getItem("nova.theme");
    const storedDensity = window.localStorage.getItem("nova.density");
    if (storedTheme === "light" || storedTheme === "dark") {
      setThemeState(storedTheme);
      applyTheme(storedTheme);
    }
    if (storedDensity === "compact" || storedDensity === "comfortable") {
      setDensityState(storedDensity);
      applyDensity(storedDensity);
    }
  }, []);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    window.localStorage.setItem("nova.theme", next);
    applyTheme(next);
  }, []);

  const setDensity = useCallback((next: Density) => {
    setDensityState(next);
    window.localStorage.setItem("nova.density", next);
    applyDensity(next);
  }, []);

  // Connection health, refreshed on mount and every 30 seconds.
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [checking, setChecking] = useState(true);

  const refresh = useCallback(() => {
    setChecking(true);
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
      .finally(() => setChecking(false));
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 30_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  // Conversations.
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    setConversations(loadConversations());
  }, []);

  const persist = useCallback((next: Conversation[]) => {
    setConversations(next);
    saveConversations(next);
  }, []);

  const startNew = useCallback(() => {
    // Reuse an existing empty chat instead of piling up blanks.
    const existingEmpty = conversations.find(
      (conversation) => conversation.messages.length === 0,
    );
    if (existingEmpty) {
      setActiveId(existingEmpty.id);
      return;
    }
    const fresh = newConversation();
    persist([fresh, ...conversations]);
    setActiveId(fresh.id);
  }, [conversations, persist]);

  const ensureActive = useCallback((): string => {
    if (
      activeId &&
      conversations.some((conversation) => conversation.id === activeId)
    ) {
      return activeId;
    }
    const existingEmpty = conversations.find(
      (conversation) => conversation.messages.length === 0,
    );
    if (existingEmpty) {
      setActiveId(existingEmpty.id);
      return existingEmpty.id;
    }
    const fresh = newConversation();
    persist([fresh, ...conversations]);
    setActiveId(fresh.id);
    return fresh.id;
  }, [activeId, conversations, persist]);

  const setMessages = useCallback(
    (id: string, messages: StoredMessage[]) => {
      setConversations((current) => {
        const next = current
          .map((conversation) =>
            conversation.id === id
              ? {
                  ...conversation,
                  messages,
                  title: titleFor(messages),
                  updatedAt: Date.now(),
                }
              : conversation,
          )
          .sort((a, b) => b.updatedAt - a.updatedAt);
        saveConversations(next);
        return next;
      });
    },
    [],
  );

  const remove = useCallback(
    (id: string) => {
      persist(conversations.filter((conversation) => conversation.id !== id));
      if (activeId === id) setActiveId(null);
    },
    [conversations, activeId, persist],
  );

  const clearAll = useCallback(() => {
    persist([]);
    setActiveId(null);
  }, [persist]);

  const preferences = useMemo(
    () => ({ theme, density, setTheme, setDensity }),
    [theme, density, setTheme, setDensity],
  );
  const connection = useMemo(
    () => ({ health, checking, refresh }),
    [health, checking, refresh],
  );
  const conversationsApi = useMemo<ConversationsApi>(
    () => ({
      conversations,
      activeId,
      active:
        conversations.find((conversation) => conversation.id === activeId) ??
        null,
      select: setActiveId,
      startNew,
      ensureActive,
      setMessages,
      remove,
      clearAll,
    }),
    [
      conversations,
      activeId,
      startNew,
      ensureActive,
      setMessages,
      remove,
      clearAll,
    ],
  );

  return (
    <PreferencesContext.Provider value={preferences}>
      <ConnectionContext.Provider value={connection}>
        <ConversationsContext.Provider value={conversationsApi}>
          {children}
        </ConversationsContext.Provider>
      </ConnectionContext.Provider>
    </PreferencesContext.Provider>
  );
}

/* -------------------------------------------------------------- hooks --- */

export function usePreferences(): Preferences {
  const context = useContext(PreferencesContext);
  if (!context) throw new Error("usePreferences outside <Providers>");
  return context;
}

export function useConnection(): Connection {
  const context = useContext(ConnectionContext);
  if (!context) throw new Error("useConnection outside <Providers>");
  return context;
}

export function useConversations(): ConversationsApi {
  const context = useContext(ConversationsContext);
  if (!context) throw new Error("useConversations outside <Providers>");
  return context;
}
