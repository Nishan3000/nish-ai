"use client";

import { AlertCircle, X } from "lucide-react";

/** Inline, dismissible error with a plain-language message. */
export default function ErrorBanner({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-lg border px-4 py-3 text-sm"
      style={{
        borderColor: "var(--warn)",
        color: "var(--warn)",
        background: "var(--warn-soft)",
      }}
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="flex-1">{message}</span>
      {onDismiss && (
        <button onClick={onDismiss} aria-label="Dismiss error">
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
