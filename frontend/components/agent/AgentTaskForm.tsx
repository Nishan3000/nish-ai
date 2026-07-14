"use client";

/**
 * Task submission form for the coding agent. Planning runs on the local
 * model and can take a while — the form shows an honest progress state
 * and offers Cancel (aborts the request client-side).
 */

import { Bot, Square } from "lucide-react";
import { useState } from "react";

import NovaLogo from "@/components/NovaLogo";

export default function AgentTaskForm({
  onSubmit,
  onCancel,
  busy,
}: {
  onSubmit: (description: string) => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const [description, setDescription] = useState("");

  const submit = () => {
    const trimmed = description.trim();
    if (trimmed.length < 5 || busy) return;
    onSubmit(trimmed);
    setDescription("");
  };

  return (
    <div
      className="rounded-xl border p-4"
      style={{ borderColor: "var(--line)", background: "var(--surface)" }}
    >
      <label
        htmlFor="task-description"
        className="mb-2 flex items-center gap-2 text-sm font-medium"
      >
        <Bot className="h-4 w-4" style={{ color: "var(--nova)" }} />
        Describe a development task
      </label>
      <textarea
        id="task-description"
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            submit();
          }
        }}
        placeholder="e.g. Add input validation to the user registration endpoint"
        rows={3}
        maxLength={4000}
        disabled={busy}
        className="w-full resize-none rounded-lg border bg-transparent px-3 py-2 text-sm outline-none placeholder:text-[var(--dim)] focus:border-[var(--nova)]"
        style={{ borderColor: "var(--line)" }}
      />
      <div className="mt-3 flex items-center justify-between gap-3">
        <p className="text-xs" style={{ color: "var(--dim)" }}>
          Nova will inspect the workspace and produce a step-by-step plan for
          your review. Nothing is modified.
        </p>
        {busy ? (
          <button
            onClick={onCancel}
            className="flex shrink-0 items-center gap-1.5 rounded-lg border px-3.5 py-2 text-sm font-medium hover:bg-[var(--surface-2)]"
            style={{ borderColor: "var(--line)" }}
          >
            <Square className="h-3.5 w-3.5" style={{ color: "var(--warn)" }} />
            Cancel
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={description.trim().length < 5}
            className="shrink-0 rounded-lg px-3.5 py-2 text-sm font-medium transition-opacity disabled:opacity-40"
            style={{ background: "var(--nova)", color: "var(--bg)" }}
          >
            Analyse project
          </button>
        )}
      </div>
      {busy && (
        <div
          className="mt-3 flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm"
          style={{ background: "var(--nova-soft)" }}
          aria-live="polite"
        >
          <NovaLogo pulsing />
          Planning with your local model — this can take a minute or two…
        </div>
      )}
    </div>
  );
}
