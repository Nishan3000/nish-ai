"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import MessageBubble from "@/components/MessageBubble";
import { ApiError, getHealth, sendChat } from "@/lib/api";
import type { ChatMessage, HealthResponse } from "@/types/chat";

/** Small four-pointed star — Nova's mark. Pulses while thinking. */
function NovaStar({ pulsing }: { pulsing: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={`h-4 w-4 ${pulsing ? "nova-pulse" : ""}`}
      style={{ color: "var(--nova)" }}
      aria-hidden="true"
    >
      <path
        d="M12 2 L14.2 9.8 L22 12 L14.2 14.2 L12 22 L9.8 14.2 L2 12 L9.8 9.8 Z"
        fill="currentColor"
      />
    </svg>
  );
}

export default function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // One health check on mount: tells the user immediately whether the
  // backend and Ollama are up, before they type anything.
  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  // Keep the newest message in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isThinking]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isThinking) return;

    const nextMessages: ChatMessage[] = [
      ...messages,
      { role: "user", content: text },
    ];
    setMessages(nextMessages);
    setInput("");
    setError(null);
    setIsThinking(true);

    try {
      const response = await sendChat(nextMessages);
      setMessages([
        ...nextMessages,
        { role: "assistant", content: response.reply },
      ]);
    } catch (err) {
      // Show the failure but keep the user's message in the transcript so
      // nothing typed is ever lost; they can just press send again.
      setError(
        err instanceof ApiError ? err.message : "Something went wrong.",
      );
    } finally {
      setIsThinking(false);
      textareaRef.current?.focus();
    }
  }, [input, isThinking, messages]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends; Shift+Enter inserts a newline.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };

  const ollamaUp = health?.ollama === "reachable";

  return (
    <div className="mx-auto flex h-dvh max-w-3xl flex-col px-4">
      {/* Header */}
      <header
        className="flex items-center justify-between border-b py-4"
        style={{ borderColor: "var(--line)" }}
      >
        <div className="flex items-center gap-2.5">
          <NovaStar pulsing={isThinking} />
          <h1 className="font-display text-lg font-medium tracking-wide">
            Nova
          </h1>
        </div>
        <div
          className="flex items-center gap-2 text-xs"
          style={{ color: "var(--dim)" }}
        >
          <span
            className="inline-block h-1.5 w-1.5 rounded-full"
            style={{ background: ollamaUp ? "var(--ok)" : "var(--warn)" }}
            aria-hidden="true"
          />
          {health === null
            ? "Backend offline"
            : ollamaUp
              ? `${health.ollama_model} · local`
              : "Ollama offline"}
        </div>
      </header>

      {/* Transcript */}
      <main className="flex-1 space-y-5 overflow-y-auto py-6">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <NovaStar pulsing={false} />
            <p className="font-display text-xl">Ask Nova anything</p>
            <p className="max-w-sm text-sm" style={{ color: "var(--dim)" }}>
              Everything runs on your machine. This conversation is held in
              your browser and sent only to your local model.
            </p>
          </div>
        )}

        {messages.map((message, index) => (
          <MessageBubble key={index} message={message} />
        ))}

        {isThinking && (
          <div
            className="flex items-center gap-2 text-sm"
            style={{ color: "var(--dim)" }}
          >
            <NovaStar pulsing />
            Thinking…
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="rounded-lg border px-4 py-3 text-sm"
            style={{ borderColor: "var(--warn)", color: "var(--warn)" }}
          >
            {error}
          </div>
        )}

        <div ref={bottomRef} />
      </main>

      {/* Composer */}
      <footer className="pb-5">
        <div
          className="flex items-end gap-2 rounded-2xl border p-2 focus-within:border-[var(--nova)]"
          style={{ background: "var(--panel)", borderColor: "var(--line)" }}
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message Nova…"
            rows={1}
            maxLength={8000}
            aria-label="Message Nova"
            className="max-h-40 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] outline-none placeholder:text-[var(--dim)]"
          />
          <button
            onClick={() => void handleSend()}
            disabled={!input.trim() || isThinking}
            className="rounded-xl px-4 py-2 font-display text-sm font-medium transition-opacity disabled:opacity-40"
            style={{ background: "var(--nova)", color: "var(--void)" }}
          >
            Send
          </button>
        </div>
        <p
          className="mt-2 text-center text-xs"
          style={{ color: "var(--dim)" }}
        >
          Enter to send · Shift+Enter for a new line
        </p>
      </footer>
    </div>
  );
}
