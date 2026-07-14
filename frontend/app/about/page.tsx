"use client";

/**
 * About NISH — the application's identity, served by GET /api/identity.
 * All fields are read-only by design: identity is configured on the
 * backend (identity.json), and there is deliberately no edit UI because
 * no secured update endpoint exists.
 */

import { Cpu, RefreshCw, User } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import ErrorBanner from "@/components/ErrorBanner";
import NishLogo from "@/components/NishLogo";
import { ApiError, getIdentity } from "@/lib/api";
import type { IdentityInfo } from "@/types/identity";

function FactRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-3">
      <span className="text-sm" style={{ color: "var(--dim)" }}>
        {label}
      </span>
      <span className="text-sm font-medium">{value}</span>
    </div>
  );
}

export default function AboutPage() {
  const [identity, setIdentity] = useState<IdentityInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getIdentity()
      .then(setIdentity)
      .catch((err) => {
        setError(
          err instanceof ApiError
            ? err.message
            : "Could not load identity information.",
        );
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div
        className="flex h-full items-center justify-center gap-2.5 text-sm"
        style={{ color: "var(--dim)" }}
      >
        <NishLogo pulsing />
        Loading identity…
      </div>
    );
  }

  if (error || identity === null) {
    return (
      <div className="mx-auto w-full max-w-xl space-y-3 px-4 py-8">
        <ErrorBanner
          message={
            error ??
            "Identity information is unavailable. Is the backend running?"
          }
        />
        <button
          onClick={load}
          className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm hover:bg-[var(--surface-2)]"
          style={{ borderColor: "var(--line)" }}
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4 px-4 py-8">
      {/* Hero */}
      <div className="flex flex-col items-center gap-2 py-4 text-center">
        <NishLogo className="h-8 w-8" />
        <h2 className="font-display text-3xl font-medium">{identity.name}</h2>
        <p
          className="font-display text-sm font-medium uppercase tracking-widest"
          style={{ color: "var(--nova)" }}
        >
          {identity.tagline}
        </p>
        <p
          className="mt-1 max-w-lg text-sm leading-relaxed"
          style={{ color: "var(--dim)" }}
        >
          {identity.purpose}
        </p>
      </div>

      {/* Facts (read-only by design) */}
      <section
        className="divide-y rounded-xl border"
        style={{ borderColor: "var(--line)", background: "var(--surface)" }}
      >
        <FactRow label="Creator" value={identity.creator} />
        <FactRow label="Lead developer" value={identity.lead_developer} />
        <FactRow
          label="Project started"
          value={String(identity.project_started)}
        />
        <FactRow label="Company" value={identity.company} />
        <FactRow label="Version" value={identity.version} />
      </section>

      {/* Model — clearly distinguished from the application */}
      <section
        className="rounded-xl border p-4"
        style={{ borderColor: "var(--line)", background: "var(--surface)" }}
      >
        <h3 className="mb-1 flex items-center gap-2 text-sm font-medium">
          <Cpu className="h-4 w-4" style={{ color: "var(--nova)" }} />
          Language model
        </h3>
        <p className="text-sm">
          <span className="font-mono">{identity.current_model}</span>
          <span style={{ color: "var(--dim)" }}>
            {" "}
            · {identity.model_runtime}
          </span>
        </p>
        <p className="mt-2 text-xs leading-relaxed" style={{ color: "var(--dim)" }}>
          {identity.name} is the application, created by {identity.creator}.
          The language model above provides its current text capabilities and
          was not created by {identity.creator} — the two are separate, and{" "}
          {identity.name} will say so if you ask.
        </p>
      </section>

      {/* Personality */}
      <section
        className="rounded-xl border p-4"
        style={{ borderColor: "var(--line)", background: "var(--surface)" }}
      >
        <h3 className="mb-1 flex items-center gap-2 text-sm font-medium">
          <User className="h-4 w-4" style={{ color: "var(--nova)" }} />
          Personality & principles
        </h3>
        <p className="text-sm" style={{ color: "var(--dim)" }}>
          {identity.personality_style}
        </p>
        <ul
          className="mt-2 list-disc space-y-1 pl-5 text-sm"
          style={{ color: "var(--dim)" }}
        >
          {identity.principles.map((principle, index) => (
            <li key={index}>{principle}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
