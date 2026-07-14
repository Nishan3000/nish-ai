import NovaLogo from "@/components/NovaLogo";

/** Animated "Nova is thinking" indicator. */
export default function TypingIndicator() {
  return (
    <div
      className="flex items-center gap-2.5 text-sm"
      style={{ color: "var(--dim)" }}
      aria-live="polite"
      aria-label="Nova is thinking"
    >
      <NovaLogo pulsing />
      <span className="flex gap-1">
        <span className="typing-dot inline-block h-1.5 w-1.5 rounded-full bg-current" />
        <span className="typing-dot inline-block h-1.5 w-1.5 rounded-full bg-current" />
        <span className="typing-dot inline-block h-1.5 w-1.5 rounded-full bg-current" />
      </span>
    </div>
  );
}
