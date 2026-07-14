"use client";

/**
 * The chat page's brain: connects the conversation store, the composer,
 * the message list, and the backend. Messages persist to localStorage
 * through the conversations context, so history survives reloads.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import ErrorBanner from "@/components/ErrorBanner";
import { useConversations } from "@/components/Providers";
import ChatComposer from "@/components/chat/ChatComposer";
import ChatMessage from "@/components/chat/ChatMessage";
import TypingIndicator from "@/components/chat/TypingIndicator";
import WelcomeScreen from "@/components/chat/WelcomeScreen";
import { AbortedError, ApiError, sendChat } from "@/lib/api";
import type { StoredMessage } from "@/types/conversation";

export default function ChatView() {
  const { active, ensureActive, setMessages } = useConversations();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const messages = active?.messages ?? [];

  // Keep the newest message in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, busy]);

  // Abort any in-flight request when leaving the page.
  useEffect(() => () => abortRef.current?.abort(), []);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;

      // Get (or synchronously create) the conversation to write into.
      const targetId = ensureActive();

      const userMessage: StoredMessage = {
        role: "user",
        content: trimmed,
        at: Date.now(),
      };
      const history = [...messages, userMessage];
      setMessages(targetId, history);

      setInput("");
      setError(null);
      setBusy(true);
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await sendChat(
          history.map(({ role, content }) => ({ role, content })),
          controller.signal,
        );
        const reply: StoredMessage = {
          role: "assistant",
          content: response.reply,
          at: Date.now(),
          memoriesUsed: response.memories_used,
        };
        setMessages(targetId, [...history, reply]);
      } catch (err) {
        if (err instanceof AbortedError) {
          // User pressed Stop: keep their message, no error banner.
        } else if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Something went wrong. Please try again.");
        }
      } finally {
        setBusy(false);
        abortRef.current = null;
      }
    },
    [busy, ensureActive, messages, setMessages],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const hasConversation = messages.length > 0;

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        {!hasConversation ? (
          <WelcomeScreen onPick={(prompt) => setInput(prompt)} />
        ) : (
          <div
            className="mx-auto flex w-full max-w-3xl flex-col px-4 py-6"
            style={{ gap: "var(--msg-gap)" }}
          >
            {messages.map((message, index) => (
              <ChatMessage key={`${message.at}-${index}`} message={message} />
            ))}
            {busy && <TypingIndicator />}
            {error && (
              <ErrorBanner message={error} onDismiss={() => setError(null)} />
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
      <ChatComposer
        value={input}
        onChange={setInput}
        onSend={() => void send(input)}
        onStop={stop}
        busy={busy}
      />
    </div>
  );
}
