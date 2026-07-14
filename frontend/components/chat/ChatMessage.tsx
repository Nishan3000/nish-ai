"use client";

/**
 * One chat message. User messages: raised bubble on the right, plain
 * text. Nova's replies: left-aligned with the gold rule, rendered as
 * markdown. Timestamps appear on hover (title) — visible chrome only
 * when useful.
 */

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
      </div>
    </div>
  );
}
