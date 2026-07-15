"use client";

/** Validation results + deterministic review findings. */

import {
  CheckCircle2,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";

import type { Review, ValidationRun } from "@/types/coding";

export default function ReviewView({
  review,
  validations,
}: {
  review: Review | null;
  validations: ValidationRun[];
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <section
        className="rounded-xl border p-4"
        style={{ borderColor: "var(--line)", background: "var(--surface)" }}
      >
        <h3 className="mb-2 text-sm font-medium">Validation results</h3>
        {validations.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--dim)" }}>
            No commands run yet.
          </p>
        ) : (
          <ul className="space-y-2">
            {validations.map((run, index) => (
              <li key={index} className="text-sm">
                <span className="flex items-center gap-1.5">
                  {run.passed ? (
                    <CheckCircle2 className="h-3.5 w-3.5" style={{ color: "var(--ok)" }} />
                  ) : (
                    <XCircle className="h-3.5 w-3.5" style={{ color: "var(--warn)" }} />
                  )}
                  <code className="font-mono text-xs">{run.command}</code>
                  <span className="text-xs" style={{ color: "var(--dim)" }}>
                    {run.timed_out
                      ? "timed out"
                      : `exit ${run.exit_code} · ${run.duration_ms} ms`}
                  </span>
                </span>
                {run.output_excerpt && !run.passed && (
                  <pre
                    className="mt-1 max-h-32 overflow-auto rounded-md border px-2 py-1.5 font-mono text-xs"
                    style={{ borderColor: "var(--line)", color: "var(--dim)" }}
                  >
                    {run.output_excerpt.slice(0, 1500)}
                  </pre>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section
        className="rounded-xl border p-4"
        style={{ borderColor: "var(--line)", background: "var(--surface)" }}
      >
        <h3 className="mb-2 flex items-center gap-2 text-sm font-medium">
          {review && review.findings.some((f) => f.severity === "high") ? (
            <ShieldAlert className="h-4 w-4" style={{ color: "var(--warn)" }} />
          ) : (
            <ShieldCheck className="h-4 w-4" style={{ color: "var(--ok)" }} />
          )}
          Security & code review
        </h3>
        {review === null ? (
          <p className="text-sm" style={{ color: "var(--dim)" }}>
            Review runs after a proposal exists.
          </p>
        ) : (
          <>
            {review.findings.length === 0 && (
              <p className="text-sm" style={{ color: "var(--ok)" }}>
                No security findings.
              </p>
            )}
            <ul className="space-y-1.5">
              {review.findings.map((finding, index) => (
                <li key={index} className="text-sm">
                  <span
                    className="mr-1.5 rounded px-1.5 py-0.5 text-xs font-medium"
                    style={{
                      background:
                        finding.severity === "high"
                          ? "var(--warn-soft)"
                          : "var(--nova-soft)",
                      color:
                        finding.severity === "high"
                          ? "var(--warn)"
                          : "var(--nova)",
                    }}
                  >
                    {finding.severity}
                  </span>
                  <code className="font-mono text-xs">{finding.path}</code>
                  <span style={{ color: "var(--dim)" }}> — {finding.message}</span>
                </li>
              ))}
            </ul>
            {review.notes.length > 0 && (
              <ul
                className="mt-2 list-disc space-y-0.5 pl-5 text-xs"
                style={{ color: "var(--dim)" }}
              >
                {review.notes.map((note, index) => (
                  <li key={index}>{note}</li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>
    </div>
  );
}
