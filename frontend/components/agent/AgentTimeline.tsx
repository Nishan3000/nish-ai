"use client";

/**
 * Renders one agent task: its lifecycle history, the plan the local
 * model produced (steps, assumptions, risks, target files), and an
 * approval control that is honestly disabled — the backend cannot yet
 * modify code, and the UI never pretends otherwise.
 */

import {
  CheckCircle2,
  CircleDashed,
  Eye,
  FlaskConical,
  Pencil,
  ShieldCheck,
  XCircle,
} from "lucide-react";

import type { AgentTask, StepKind } from "@/types/agent";

const KIND_META: Record<StepKind, { icon: typeof Eye; label: string }> = {
  inspect: { icon: Eye, label: "Inspect" },
  modify: { icon: Pencil, label: "Modify" },
  test: { icon: FlaskConical, label: "Test" },
  review: { icon: ShieldCheck, label: "Review" },
};

function StateBadge({ state }: { state: AgentTask["state"] }) {
  const isGood = state === "planned" || state === "completed";
  const isBad = state === "failed" || state === "rejected";
  const Icon = isGood ? CheckCircle2 : isBad ? XCircle : CircleDashed;
  const color = isGood ? "var(--ok)" : isBad ? "var(--warn)" : "var(--dim)";
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium"
      style={{ borderColor: "var(--line)", color }}
    >
      <Icon className="h-3.5 w-3.5" />
      {state.replace(/_/g, " ")}
    </span>
  );
}

export default function AgentTimeline({ task }: { task: AgentTask }) {
  return (
    <div
      className="rounded-xl border"
      style={{ borderColor: "var(--line)", background: "var(--surface)" }}
    >
      {/* Header */}
      <div
        className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3"
        style={{ borderColor: "var(--line)" }}
      >
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{task.description}</p>
          <p className="text-xs" style={{ color: "var(--dim)" }}>
            Task {task.id} ·{" "}
            {new Date(task.created_at).toLocaleString(undefined, {
              day: "numeric",
              month: "short",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
        </div>
        <StateBadge state={task.state} />
      </div>

      <div className="space-y-4 px-4 py-4">
        {/* Lifecycle history */}
        {task.history.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <span style={{ color: "var(--dim)" }}>Lifecycle:</span>
            {["pending", ...task.history.map((record) => record.to_state)].map(
              (state, index, all) => (
                <span key={index} className="flex items-center gap-1.5">
                  <span
                    className="rounded px-1.5 py-0.5"
                    style={{ background: "var(--surface-2)" }}
                  >
                    {state.replace(/_/g, " ")}
                  </span>
                  {index < all.length - 1 && (
                    <span style={{ color: "var(--dim)" }}>→</span>
                  )}
                </span>
              ),
            )}
          </div>
        )}

        {task.error && (
          <p className="text-sm" style={{ color: "var(--warn)" }}>
            {task.error}
          </p>
        )}

        {/* Plan */}
        {task.plan && (
          <>
            <div>
              <h3 className="text-sm font-medium">Goal</h3>
              <p className="mt-1 text-sm" style={{ color: "var(--dim)" }}>
                {task.plan.goal}
              </p>
            </div>

            <div>
              <h3 className="mb-2 text-sm font-medium">
                Steps ({task.plan.steps.length})
              </h3>
              <ol className="space-y-2">
                {task.plan.steps.map((step) => {
                  const meta = KIND_META[step.kind];
                  const Icon = meta.icon;
                  return (
                    <li
                      key={step.id}
                      className="flex gap-3 rounded-lg border px-3 py-2.5"
                      style={{ borderColor: "var(--line)" }}
                    >
                      <Icon
                        className="mt-0.5 h-4 w-4 shrink-0"
                        style={{ color: "var(--nova)" }}
                        aria-label={meta.label}
                      />
                      <div className="min-w-0">
                        <p className="text-sm font-medium">
                          {step.id}. {step.title}
                          <span
                            className="ml-2 text-xs font-normal"
                            style={{ color: "var(--dim)" }}
                          >
                            {meta.label}
                          </span>
                        </p>
                        <p
                          className="mt-0.5 text-sm"
                          style={{ color: "var(--dim)" }}
                        >
                          {step.description}
                        </p>
                        {step.target_files.length > 0 && (
                          <p className="mt-1 truncate font-mono text-xs">
                            {step.target_files.join(", ")}
                          </p>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>

            {(task.plan.assumptions.length > 0 ||
              task.plan.risks.length > 0) && (
              <div className="grid gap-4 sm:grid-cols-2">
                {task.plan.assumptions.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium">Assumptions</h3>
                    <ul
                      className="mt-1 list-disc pl-5 text-sm"
                      style={{ color: "var(--dim)" }}
                    >
                      {task.plan.assumptions.map((assumption, index) => (
                        <li key={index}>{assumption}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {task.plan.risks.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium">Risks</h3>
                    <ul
                      className="mt-1 list-disc pl-5 text-sm"
                      style={{ color: "var(--dim)" }}
                    >
                      {task.plan.risks.map((risk, index) => (
                        <li key={index}>{risk}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Honest approval control */}
            <div
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2.5"
              style={{ borderColor: "var(--line)", background: "var(--surface-2)" }}
            >
              <p className="text-xs" style={{ color: "var(--dim)" }}>
                Code changes are not implemented yet — NISH can currently plan
                and read, not write. Approval will unlock once the
                modification phase ships.
              </p>
              <button
                disabled
                className="cursor-not-allowed rounded-lg border px-3 py-1.5 text-sm opacity-50"
                style={{ borderColor: "var(--line)" }}
                title="Available after the code-modification phase"
              >
                Approve changes
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
