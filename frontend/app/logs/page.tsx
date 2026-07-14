"use client";

/**
 * Activity Logs page. The backend currently exposes two windows into
 * agent activity: the audit chain verification result and each task's
 * transition history. Both are shown here; a raw audit-entry feed will
 * follow when the backend adds an endpoint for it (the data already
 * exists server-side in the hash-chained JSONL log).
 */

import { ListChecks, RefreshCw, ShieldCheck, ShieldX } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import ErrorBanner from "@/components/ErrorBanner";
import { ApiError, listAgentTasks, verifyAudit } from "@/lib/api";
import type { AgentTask, AuditVerify } from "@/types/agent";

interface LogRow {
  at: string;
  taskId: string;
  text: string;
}

function rowsFrom(tasks: AgentTask[]): LogRow[] {
  const rows: LogRow[] = [];
  for (const task of tasks) {
    rows.push({
      at: task.created_at,
      taskId: task.id,
      text: `Task created: "${task.description.slice(0, 80)}"`,
    });
    for (const record of task.history) {
      rows.push({
        at: record.at,
        taskId: task.id,
        text:
          `State: ${record.from_state.replace(/_/g, " ")} → ` +
          `${record.to_state.replace(/_/g, " ")}` +
          (record.note ? ` — ${record.note}` : ""),
      });
    }
  }
  return rows.sort(
    (a, b) => new Date(b.at).getTime() - new Date(a.at).getTime(),
  );
}

export default function LogsPage() {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [audit, setAudit] = useState<AuditVerify | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [taskList, auditStatus] = await Promise.all([
        listAgentTasks(),
        verifyAudit(),
      ]);
      setTasks(taskList.tasks);
      setAudit(auditStatus);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not load activity data.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const rows = rowsFrom(tasks);

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4 px-4 py-6">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-medium">
          <ListChecks className="h-4 w-4" style={{ color: "var(--nova)" }} />
          Agent activity
        </h2>
        <button
          onClick={() => void refresh()}
          className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm hover:bg-[var(--surface-2)]"
          style={{ borderColor: "var(--line)" }}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {/* Audit integrity */}
      <section
        className="flex items-start gap-3 rounded-xl border p-4"
        style={{ borderColor: "var(--line)", background: "var(--surface)" }}
      >
        {audit?.ok === false ? (
          <ShieldX className="mt-0.5 h-4 w-4 shrink-0" style={{ color: "var(--warn)" }} />
        ) : (
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" style={{ color: "var(--ok)" }} />
        )}
        <div>
          <p className="text-sm font-medium">
            Audit log integrity:{" "}
            {audit === null
              ? "unknown (backend unreachable)"
              : audit.ok
                ? "verified"
                : "TAMPERING DETECTED"}
          </p>
          <p className="text-xs" style={{ color: "var(--dim)" }}>
            {audit?.message ??
              "Every agent action is recorded in a hash-chained, append-only log on the backend."}
          </p>
        </div>
      </section>

      {/* Event feed derived from task histories */}
      <section
        className="rounded-xl border"
        style={{ borderColor: "var(--line)", background: "var(--surface)" }}
      >
        {loading ? (
          <p className="px-4 py-6 text-sm" style={{ color: "var(--dim)" }}>
            Loading activity…
          </p>
        ) : rows.length === 0 ? (
          <p className="px-4 py-6 text-sm" style={{ color: "var(--dim)" }}>
            No agent activity yet. Create a task on the Coding Agent page and
            its lifecycle will appear here.
          </p>
        ) : (
          <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
            {rows.map((row, index) => (
              <li
                key={index}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2.5 text-sm"
              >
                <span
                  className="shrink-0 font-mono text-xs"
                  style={{ color: "var(--dim)" }}
                >
                  {new Date(row.at).toLocaleString(undefined, {
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </span>
                <span
                  className="shrink-0 rounded px-1.5 py-0.5 font-mono text-xs"
                  style={{ background: "var(--surface-2)" }}
                >
                  {row.taskId}
                </span>
                <span className="min-w-0">{row.text}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
