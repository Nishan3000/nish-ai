import { Brain } from "lucide-react";

/** Placeholder until the long-term memory phase (pgvector). */
export default function MemoryPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-4 text-center">
      <span
        className="flex h-12 w-12 items-center justify-center rounded-2xl"
        style={{ background: "var(--nova-soft)" }}
      >
        <Brain className="h-5 w-5" style={{ color: "var(--nova)" }} />
      </span>
      <h2 className="font-display text-xl font-medium">Memory</h2>
      <p className="max-w-md text-sm leading-relaxed" style={{ color: "var(--dim)" }}>
        Long-term memory is planned for a later phase. Nova will remember
        useful details across conversations using semantic search over a
        local database — nothing stored in the cloud. For now, chats are
        kept only in this browser.
      </p>
    </div>
  );
}
