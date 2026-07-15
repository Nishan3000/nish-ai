"use client";

/**
 * Apply panel — the v0.7 lifecycle after approval:
 * proposal hash + expiry → "Apply to branch" with a second confirmation
 * → progress → branch/commit/final diff → rollback (also confirmed).
 *
 * The panel is explicit at every step that everything stays local:
 * nothing is ever pushed, merged, or deployed.
 */

import {
  AlertTriangle,
  CheckCircle2,
  GitBranch,
  GitCommitHorizontal,
  Undo2,
} from "lucide-react";
import { useState } from "react";

import NishLogo from "@/components/NishLogo";
import DiffView from "@/components/coding/DiffView";
import type { Approval, ChangeApplication } from "@/types/coding";

const STATUS_LABELS: Record<string, { label: string; tone: string }> = {
  approved: { label: "Approved — not applied", tone: "var(--nova)" },
  expired: { label: "Approval expired", tone: "var(--warn)" },
  applying: { label: "Applying…", tone: "var(--nova)" },
  validation_failed: { label: "Validation failed — nothing committed", tone: "var(--warn)" },
  failed: { label: "Application failed — repository restored", tone: "var(--warn)" },
  committed: { label: "Committed locally", tone: "var(--ok)" },
  rolled_back: { label: "Rolled back", tone: "var(--dim)" },
};

function approvalExpired(approval: Approval): boolean {
  return (
    approval.expires_at !== null &&
    new Date(approval.expires_at).getTime() < Date.now()
  );
}

export default function ApplyPanel({
  approval,
  application,
  busy,
  onApply,
  onRollback,
}: {
  approval: Approval;
  application: ChangeApplication | null;
  busy: boolean;
  onApply: () => void;
  onRollback: () => void;
}) {
  const [confirmingApply, setConfirmingApply] = useState(false);
  const [confirmingRollback, setConfirmingRollback] = useState(false);
  const [showFinalDiff, setShowFinalDiff] = useState(false);

  const expired = approvalExpired(approval);
  const displayStatus = application?.status ?? (expired ? "expired" : "approved");
  const status = STATUS_LABELS[displayStatus] ?? {
    label: displayStatus,
    tone: "var(--dim)",
  };
  const canApply =
    !expired &&
    (!application ||
      application.status === "validation_failed" ||
      application.status === "failed" ||
      application.status === "rolled_back");

  return (
    <section
      className="space-y-3 rounded-xl border p-4"
      style={{ borderColor: "var(--line)", background: "var(--surface)" }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-medium">Reviewed change application</h3>
        <span
          className="rounded-full border px-2 py-0.5 text-xs"
          style={{ borderColor: status.tone, color: status.tone }}
        >
          {status.label}
        </span>
        {busy && (
          <span className="flex items-center gap-2 text-xs" style={{ color: "var(--dim)" }}>
            <NishLogo pulsing />
            Working…
          </span>
        )}
      </div>

      <p className="text-xs" style={{ color: "var(--dim)" }}>
        Proposal hash{" "}
        <code className="font-mono">{approval.proposal_hash?.slice(0, 16)}…</code>
        {" · "}
        {approval.expires_at && (
          <>
            approval {expired ? "expired" : "valid until"}{" "}
            {new Date(approval.expires_at).toLocaleString(undefined, {
              day: "numeric",
              month: "short",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </>
        )}
      </p>

      <p
        className="flex items-start gap-2 rounded-lg border px-3 py-2 text-xs"
        style={{ borderColor: "var(--line)", color: "var(--dim)" }}
      >
        <AlertTriangle
          className="mt-0.5 h-3.5 w-3.5 shrink-0"
          style={{ color: "var(--nova)" }}
        />
        Applying creates a new local branch and a local commit only. NISH
        never pushes, never merges into your main branch, and never
        deploys — inspecting and merging the branch stays entirely in
        your hands.
      </p>

      {/* Apply action */}
      {canApply &&
        (confirmingApply ? (
          <div
            className="space-y-2 rounded-lg border p-3"
            style={{ borderColor: "var(--nova)" }}
          >
            <p className="text-sm">
              Second confirmation: apply the reviewed proposal (hash{" "}
              <code className="font-mono text-xs">
                {approval.proposal_hash?.slice(0, 12)}…
              </code>
              ) to a new local <code className="font-mono text-xs">nish/</code>{" "}
              branch? Validation reruns first; nothing is committed if it
              fails.
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setConfirmingApply(false);
                  onApply();
                }}
                disabled={busy}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-40"
                style={{ background: "var(--nova)", color: "var(--bg)" }}
              >
                <GitBranch className="h-4 w-4" />
                Yes, apply to branch
              </button>
              <button
                onClick={() => setConfirmingApply(false)}
                className="rounded-lg border px-3 py-1.5 text-sm"
                style={{ borderColor: "var(--line)" }}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setConfirmingApply(true)}
            disabled={busy}
            className="flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium disabled:opacity-40"
            style={{ background: "var(--nova)", color: "var(--bg)" }}
          >
            <GitBranch className="h-4 w-4" />
            Apply to branch…
          </button>
        ))}
      {expired && !application && (
        <p className="text-sm" style={{ color: "var(--warn)" }}>
          This approval has expired. Review the proposal and approve it
          again to apply.
        </p>
      )}

      {/* Application result */}
      {application && (
        <div className="space-y-2 text-sm">
          {application.error && (
            <p
              className="rounded-lg border px-3 py-2"
              style={{ borderColor: "var(--warn)", color: "var(--warn)" }}
            >
              {application.error}
            </p>
          )}
          <p className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="flex items-center gap-1.5">
              <GitBranch className="h-4 w-4" style={{ color: "var(--nova)" }} />
              <code className="font-mono text-xs">{application.branch_name}</code>
            </span>
            {application.commit_hash && (
              <span className="flex items-center gap-1.5">
                <GitCommitHorizontal
                  className="h-4 w-4"
                  style={{ color: "var(--ok)" }}
                />
                <code className="font-mono text-xs">
                  {application.commit_hash.slice(0, 12)}
                </code>
              </span>
            )}
            <span className="text-xs" style={{ color: "var(--dim)" }}>
              from {application.original_branch}
            </span>
          </p>

          {application.status === "committed" && (
            <>
              <p
                className="flex items-center gap-1.5 text-xs"
                style={{ color: "var(--ok)" }}
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                Validation passed and a local commit was created. Nothing
                was pushed or merged.
              </p>
              {application.final_diff && (
                <>
                  <button
                    onClick={() => setShowFinalDiff((value) => !value)}
                    className="text-xs"
                    style={{ color: "var(--nova)" }}
                  >
                    {showFinalDiff ? "Hide" : "Show"} final diff
                  </button>
                  {showFinalDiff && <DiffView diff={application.final_diff} />}
                </>
              )}
              {confirmingRollback ? (
                <div
                  className="space-y-2 rounded-lg border p-3"
                  style={{ borderColor: "var(--warn)" }}
                >
                  <p className="text-sm">
                    Delete branch{" "}
                    <code className="font-mono text-xs">
                      {application.branch_name}
                    </code>{" "}
                    and its commit? Your other branches and work are never
                    touched; NISH refuses if you added commits of your own.
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        setConfirmingRollback(false);
                        onRollback();
                      }}
                      disabled={busy}
                      className="rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-40"
                      style={{ background: "var(--warn)", color: "var(--surface)" }}
                    >
                      Yes, roll back
                    </button>
                    <button
                      onClick={() => setConfirmingRollback(false)}
                      className="rounded-lg border px-3 py-1.5 text-sm"
                      style={{ borderColor: "var(--line)" }}
                    >
                      Keep the branch
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmingRollback(true)}
                  disabled={busy}
                  className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm disabled:opacity-40"
                  style={{ borderColor: "var(--warn)", color: "var(--warn)" }}
                >
                  <Undo2 className="h-3.5 w-3.5" />
                  Roll back…
                </button>
              )}
            </>
          )}

          {application.status === "rolled_back" && (
            <p className="text-xs" style={{ color: "var(--dim)" }}>
              The branch and commit were removed
              {application.rolled_back_at &&
                ` on ${new Date(application.rolled_back_at).toLocaleString()}`}
              . Your repository is back to{" "}
              <code className="font-mono">{application.original_branch}</code>.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
