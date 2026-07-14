"use client";

/**
 * One chat message. User messages: raised bubble on the right, plain
 * text. NISH's replies: left-aligned with the gold rule, rendered as
 * markdown. Timestamps appear on hover (title) — visible chrome only
 * when useful.
 */

import { Brain } from "lucide-react";

import Markdown from "@/components/Markdown";
import type { StoredMessage } from "@/types/conversation";

function formatTime(at: number): string {
  return new Date(at).toLocaleString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    day: "numeric",
    month: "short",
  });
}

export default function ChatMessage({ message }: { message: StoredMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end" title={formatTime(message.at)}>
        <div
          className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm px-4 text-[15px] leading-relaxed"
          style={{
            background: "var(--surface-2)",
            paddingTop: "var(--msg-pad)",
            paddingBottom: "var(--msg-pad)",
          }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start" title={formatTime(message.at)}>
      <div
        className="max-w-[92%] border-l-2 pl-4"
        style={{
          borderColor: "var(--nova)",
          paddingTop: "var(--msg-pad)",
          paddingBottom: "var(--msg-pad)",
        }}
      >
        <Markdown content={message.content} />
        {message.memoriesUsed && message.memoriesUsed.length > 0 && (
          <p
            className="mt-2 flex items-center gap-1.5 text-xs"
            style={{ color: "var(--dim)" }}
            title={message.memoriesUsed
              .map((memory) => memory.content)
              .join("\n")}
          >
            <Brain className="h-3 w-3" style={{ color: "var(--nova)" }} />
            Used {message.memoriesUsed.length} saved{" "}
            {message.memoriesUsed.length === 1 ? "memory" : "memories"}
          </p>
        )}
      </div>
    </div>
  );
}
