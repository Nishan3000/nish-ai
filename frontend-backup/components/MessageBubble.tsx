import type { ChatMessage } from "@/types/chat";

/**
 * A single message.
 *
 * User messages sit right in a raised panel; Nova's replies sit left,
 * flush with the page, marked by a thin gold rule — gold always means
 * "the model" in this UI.
 */
export default function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div
          className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm px-4 py-3 text-[15px] leading-relaxed"
          style={{ background: "var(--panel-raised)" }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div
        className="max-w-[85%] whitespace-pre-wrap border-l-2 py-1 pl-4 text-[15px] leading-relaxed"
        style={{ borderColor: "var(--nova)" }}
      >
        {message.content}
      </div>
    </div>
  );
}
