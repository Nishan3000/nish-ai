"use client";

/**
 * Coding Agent page. Shows exactly what the backend supports today:
 * task planning, guarded repository inspection, and audit-chain
 * verification. Loads existing tasks, the repo tree, and the audit
 * status on mount; creating a task refreshes everything.
 */

import { FolderTree, ShieldCheck, ShieldX } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import ErrorBanner from "@/components/ErrorBanner";
import AgentTaskForm from "@/components/agent/AgentTaskForm";
import AgentTimeline from "@/components/agent/AgentTimeline";
import {
  AbortedError,
  ApiError,
  createAgentTask,
  getRepoTree,
  listAgentTasks,
  verifyAudit,
} from "@/lib/api";
import type { AgentTask, AuditVerify, RepoTree } from "@/types/agent";

export default function AgentPage() {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [tree, setTree] = useState<RepoTree | null>(null);
  const [audit, setAudit] = useState<AuditVerify | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    // Each panel loads independently; one failing doesn't blank the rest.
    const [tasksResult, treeResult, auditResult] = await Promise.allSettled([
      listAgentTasks(),
      getRepoTree(),
      verifyAudit(),
    ]);
    if (tasksResult.status === "fulfilled") setTasks(tasksResult.value.tasks);
    if (treeResult.status === "fulfilled") setTree(treeResult.value);
    if (auditResult.status === "fulfilled") setAudit(auditResult.value);
    if (
      tasksResult.status === "rejected" &&
      tasksResult.reason instanceof ApiError
    ) {
      setError(tasksResult.reason.message);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
    return () => abortRef.current?.abort();
  }, [refresh]);

  const submit = useCallback(
    async (description: string) => {
      setBusy(true);
      setError(null);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const task = await createAgentTask(description, controller.signal);
        setTasks((current) => [task, ...current]);
        void refresh();
      } catch (err) {
        if (err instanceof AbortedError) {
          // User cancelled; the backend may still record a task — refresh.
          void refresh();
        } else if (err instanceof ApiError) {
          setError(err.message);
          void refresh(); // a failed task still appears in the list
        } else {
          setError("Something went wrong. Please try again.");
        }
      } finally {
        setBusy(false);
        abortRef.current = null;
      }
    },
    [refresh],
  );

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4 px-4 py-6">
      <AgentTaskForm
        onSubmit={(description) => void submit(description)}
        onCancel={() => abortRef.current?.abort()}
        busy={busy}
      />

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {/* Workspace + security overview */}
      <div className="grid gap-4 md:grid-cols-2">
        <section
          className="rounded-xl border p-4"
          style={{ borderColor: "var(--line)", background: "var(--surface)" }}
        >
          <h2 className="mb-2 flex items-center gap-2 text-sm font-medium">
            <FolderTree className="h-4 w-4" style={{ color: "var(--nova)" }} />
            Workspace files NISH can inspect
          </h2>
          {loading ? (
            <p className="text-sm" style={{ color: "var(--dim)" }}>
              Loading…
            </p>
          ) : tree === null ? (
            <p className="text-sm" style={{ color: "var(--dim)" }}>
              Workspace unavailable — is the backend running?
            </p>
          ) : tree.entries.length === 0 ? (
            <p className="text-sm" style={{ color: "var(--dim)" }}>
              The workspace is empty. Point AGENT_WORKSPACE_ROOT in
              backend/.env at a project.
            </p>
          ) : (
            <ul className="max-h-56 space-y-1 overflow-y-auto font-mono text-xs">
              {tree.entries.map((entry) => (
                <li key={entry.path} className="flex justify-between gap-2">
                  <span className="truncate">{entry.path}</span>
                  <span style={{ color: "var(--dim)" }}>
                    {entry.size_bytes} B
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-xs" style={{ color: "var(--dim)" }}>
            Secrets, .git internals, and anything outside the workspace are
            unreadable by design.
          </p>
        </section>

        <section
          className="rounded-xl border p-4"
          style={{ borderColor: "var(--line)", background: "var(--surface)" }}
        >
          <h2 className="mb-2 flex items-center gap-2 text-sm font-medium">
            {audit?.ok === false ? (
              <ShieldX className="h-4 w-4" style={{ color: "var(--warn)" }} />
            ) : (
              <ShieldCheck className="h-4 w-4" style={{ color: "var(--ok)" }} />
            )}
            Security check
          </h2>
          {loading ? (
            <p className="text-sm" style={{ color: "var(--dim)" }}>
              Loading…
            </p>
          ) : audit === null ? (
            <p className="text-sm" style={{ color: "var(--dim)" }}>
              Audit status unavailable — is the backend running?
            </p>
          ) : (
            <p className="text-sm">
              Audit log:{" "}
              <span
                style={{ color: audit.ok ? "var(--ok)" : "var(--warn)" }}
                className="font-medium"
              >
                {audit.ok ? "chain intact" : `tampering detected`}
              </span>
              <span className="block text-xs" style={{ color: "var(--dim)" }}>
                {audit.message}
              </span>
            </p>
          )}
          <p className="mt-2 text-xs" style={{ color: "var(--dim)" }}>
            Every agent action is written to a hash-chained, append-only log.
            The full record lives in Activity Logs.
          </p>
        </section>
      </div>

      {/* Task list */}
      <section className="space-y-3">
        <h2 className="text-sm font-medium">Tasks</h2>
        {loading ? (
          <p className="text-sm" style={{ color: "var(--dim)" }}>
            Loading tasks…
          </p>
        ) : tasks.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--dim)" }}>
            No tasks yet. Describe one above — NISH will plan it without
            touching any files.
          </p>
        ) : (
          tasks.map((task) => <AgentTimeline key={task.id} task={task} />)
        )}
      </section>
    </div>
  );
}
