"use client";

/**
 * Green dot = backend and Ollama reachable; amber = backend up but
 * Ollama down; red = backend unreachable. Click to re-check.
 */

import { useConnection } from "@/components/Providers";

export default function ConnectionStatus({
  showLabel = true,
}: {
  showLabel?: boolean;
}) {
  const { health, checking, refresh } = useConnection();

  const color =
    health === null
      ? "var(--warn)"
      : health.ollama === "reachable"
        ? "var(--ok)"
        : "var(--nova)";
  const label =
    health === null
      ? "Backend offline"
      : health.ollama === "reachable"
        ? `${health.ollama_model} · connected`
        : "Ollama offline";

  return (
    <button
      onClick={refresh}
      title="Click to re-check the connection"
      className="flex items-center gap-2 rounded-md px-2 py-1 text-xs hover:bg-[var(--surface-2)]"
      style={{ color: "var(--dim)" }}
    >
      <span
        className={`inline-block h-2 w-2 rounded-full ${checking ? "animate-pulse" : ""}`}
        style={{ background: color }}
        aria-hidden="true"
      />
      {showLabel && <span className="max-w-40 truncate">{label}</span>}
    </button>
  );
}
