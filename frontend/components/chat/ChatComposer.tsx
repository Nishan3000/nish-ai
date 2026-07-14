"use client";

/**
 * Message composer: auto-growing textarea, Send/Stop, and a disabled
 * attach button (file uploads arrive with the Files phase — the button
 * is honest about that rather than pretending).
 *
 * Enter sends, Shift+Enter inserts a newline. Send is disabled when the
 * input is empty; while Nova is thinking the button becomes Stop, which
 * aborts the in-flight request.
 */

import { Paperclip, Send, Square } from "lucide-react";
import { useEffect, useRef } from "react";

export default function ChatComposer({
  value,
  onChange,
  onSend,
  onStop,
  busy,
}: {
  value: string;
  onChange: (next: string) => void;
  onSend: () => void;
  onStop: () => void;
  busy: boolean;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow up to a max height.
  useEffect(() => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 200)}px`;
  }, [value]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (value.trim() && !busy) onSend();
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-4">
      <div
        className="flex items-end gap-1.5 rounded-2xl border p-2 focus-within:border-[var(--nova)]"
        style={{ background: "var(--surface)", borderColor: "var(--line)" }}
      >
        <button
          disabled
          aria-label="Attach a file (available in a later phase)"
          title="File uploads arrive with the Files phase"
          className="cursor-not-allowed rounded-lg p-2 opacity-40"
          style={{ color: "var(--dim)" }}
        >
          <Paperclip className="h-4 w-4" />
        </button>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message Nova…"
          rows={1}
          maxLength={8000}
          aria-label="Message Nova"
          className="max-h-[200px] flex-1 resize-none bg-transparent px-2 py-2 text-[15px] outline-none placeholder:text-[var(--dim)]"
        />
        {busy ? (
          <button
            onClick={onStop}
            aria-label="Stop generating"
            title="Stop generating"
            className="flex items-center gap-1.5 rounded-xl border px-3.5 py-2 text-sm font-medium hover:bg-[var(--surface-2)]"
            style={{ borderColor: "var(--line)" }}
          >
            <Square className="h-3.5 w-3.5" style={{ color: "var(--warn)" }} />
            Stop
          </button>
        ) : (
          <button
            onClick={onSend}
            disabled={!value.trim()}
            aria-label="Send message"
            className="flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-medium transition-opacity disabled:opacity-40"
            style={{ background: "var(--nova)", color: "var(--bg)" }}
          >
            <Send className="h-3.5 w-3.5" />
            Send
          </button>
        )}
      </div>
      <p className="mt-2 text-center text-xs" style={{ color: "var(--dim)" }}>
        Enter to send · Shift+Enter for a new line
      </p>
    </div>
  );
}
