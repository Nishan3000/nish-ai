"use client";

/**
 * Coding Agent page — the v0.6 controlled pipeline:
 * register/select project → describe task → plan → isolated workspace
 * → generate proposal → allowlisted validation → deterministic review
 * → expandable diff → approve/reject.
 *
 * Everything here is a PROPOSAL: approving records the decision but the
 * live repository is never modified in this milestone, and the UI says
 * so explicitly.
 */

import {
  ChevronDown,
  ChevronRight,
  Code2,
  FolderGit2,
  Play,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import ErrorBanner from "@/components/ErrorBanner";
import NishLogo from "@/components/NishLogo";
import DiffView from "@/components/coding/DiffView";
import PlanView from "@/components/coding/PlanView";
import RegisterProject from "@/components/coding/RegisterProject";
import ReviewView from "@/components/coding/ReviewView";
import {
  ApiError,
  codingTaskStage,
  createCodingTask,
  decideCodingTask,
  getCodingTask,
  listCodingProjects,
  listCodingTasks,
  registerCodingProject,
  scanCodingProject,
  validateCodingTask,
} from "@/lib/api";
import type {
  CodingProject,
  CodingTask,
  CodingTaskState,
  ProjectScan,
} from "@/types/coding";

/* ------------------------------------------------------------- stepper --- */

const PIPELINE: { label: string; states: CodingTaskState[] }[] = [
  { label: "Plan", states: ["created", "planning", "planned"] },
  { label: "Workspace", states: ["workspace_ready"] },
  { label: "Generate", states: ["generating", "generated"] },
  { label: "Validate", states: ["validating", "validated"] },
  { label: "Review", states: ["awaiting_approval"] },
  { label: "Decision", states: ["approved", "rejected"] },
];

function stageIndex(state: CodingTaskState): number {
  if (state === "failed") return -1;
  return PIPELINE.findIndex((stage) => stage.states.includes(state));
}

function Stepper({ state }: { state: CodingTaskState }) {
  const current = stageIndex(state);
  return (
    <ol className="flex flex-wrap items-center gap-1.5 text-xs" aria-label="Task progress">
      {PIPELINE.map((stage, index) => {
        const done = current > index;
        const active = current === index;
        return (
          <li key={stage.label} className="flex items-center gap-1.5">
            <span
              className="rounded-full border px-2 py-0.5"
              style={{
                borderColor: done || active ? "var(--nova)" : "var(--line)",
                color: active ? "var(--bg)" : done ? "var(--nova)" : "var(--dim)",
                background: active ? "var(--nova)" : "transparent",
              }}
            >
              {stage.label}
            </span>
            {index < PIPELINE.length - 1 && (
              <span style={{ color: "var(--dim)" }}>→</span>
            )}
          </li>
        );
      })}
      {state === "failed" && (
        <li
          className="rounded-full border px-2 py-0.5"
          style={{ borderColor: "var(--warn)", color: "var(--warn)" }}
        >
          Failed
        </li>
      )}
    </ol>
  );
}

/* ------------------------------------------------------- project scan --- */

function ScanPanel({ scan }: { scan: ProjectScan }) {
  const [showTree, setShowTree] = useState(false);
  return (
    <div
      className="space-y-2 rounded-xl border p-4 text-sm"
      style={{ borderColor: "var(--line)", background: "var(--surface)" }}
    >
      <p style={{ color: "var(--dim)" }}>
        {scan.files.length} files ·{" "}
        {scan.technologies.length > 0
          ? scan.technologies.join(", ")
          : "no recognised technologies"}
        {scan.git_branch
          ? ` · branch ${scan.git_branch}${
              (scan.git_dirty_files ?? 0) > 0
                ? ` (${scan.git_dirty_files} uncommitted)`
                : ""
            }`
          : ""}
      </p>
      {scan.test_commands.length > 0 && (
        <p style={{ color: "var(--dim)" }}>
          Detected test commands:{" "}
          <code className="font-mono text-xs">
            {scan.test_commands.join("  ·  ")}
          </code>
        </p>
      )}
      <button
        onClick={() => setShowTree((value) => !value)}
        className="flex items-center gap-1 text-xs"
        style={{ color: "var(--nova)" }}
      >
        {showTree ? (
          <ChevronDown className="h-3.5 w-3.5" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" />
        )}
        {showTree ? "Hide" : "Show"} file list
      </button>
      {showTree && (
        <pre
          className="max-h-72 overflow-auto rounded-lg border p-3 font-mono text-xs leading-relaxed"
          style={{ borderColor: "var(--line)" }}
        >
          {scan.files.map((file) => file.path).join("\n")}
        </pre>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- page --- */

export default function CodingAgentPage() {
  const [projects, setProjects] = useState<CodingProject[]>([]);
  const [projectId, setProjectId] = useState<string>("");
  const [registering, setRegistering] = useState(false);
  const [scan, setScan] = useState<ProjectScan | null>(null);
  const [scanLoading, setScanLoading] = useState(false);

  const [tasks, setTasks] = useState<CodingTask[]>([]);
  const [task, setTask] = useState<CodingTask | null>(null);
  const [description, setDescription] = useState("");

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null); // current action label
  const [error, setError] = useState<string | null>(null);
  const [decisionMessage, setDecisionMessage] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await listCodingProjects();
      setProjects(list);
      if (list.length > 0) {
        setProjectId((current) => current || list[0].id);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load projects.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  // Load scan + recent tasks whenever the selected project changes.
  useEffect(() => {
    if (!projectId) return;
    setScan(null);
    setTask(null);
    setDecisionMessage(null);
    setScanLoading(true);
    void (async () => {
      try {
        const [scanResult, taskList] = await Promise.all([
          scanCodingProject(projectId),
          listCodingTasks(projectId),
        ]);
        setScan(scanResult);
        setTasks(taskList);
      } catch (err) {
        setError(
          err instanceof ApiError ? err.message : "Could not inspect project.",
        );
      } finally {
        setScanLoading(false);
      }
    })();
  }, [projectId]);

  const run = async (label: string, action: () => Promise<CodingTask>) => {
    setBusy(label);
    setError(null);
    try {
      setTask(await action());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `${label} failed.`);
      // The task may have moved to "failed" server-side — refresh it.
      if (task) {
        try {
          setTask(await getCodingTask(task.id));
        } catch {
          /* keep the previous snapshot */
        }
      }
    } finally {
      setBusy(null);
    }
  };

  const handleRegister = async (data: {
    name: string;
    root_path: string;
    description: string;
  }) => {
    setBusy("register");
    setError(null);
    try {
      const project = await registerCodingProject(data);
      setRegistering(false);
      await loadProjects();
      setProjectId(project.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed.");
    } finally {
      setBusy(null);
    }
  };

  const handleAnalyse = () =>
    run("analyse", () =>
      createCodingTask({ project_id: projectId, description: description.trim() }),
    );

  const handleDecision = async (decision: "approved" | "rejected") => {
    if (!task) return;
    setBusy(decision);
    setError(null);
    try {
      const result = await decideCodingTask(task.id, decision);
      setDecisionMessage(result.message);
      setTask(await getCodingTask(task.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Decision failed.");
    } finally {
      setBusy(null);
    }
  };

  /** The single "next step" action for the current task state. */
  const nextAction = (): { label: string; onClick: () => void } | null => {
    if (!task || busy) return null;
    switch (task.state) {
      case "planned":
        return {
          label: "Create isolated workspace",
          onClick: () =>
            void run("workspace", () => codingTaskStage(task.id, "workspace")),
        };
      case "workspace_ready":
        return {
          label: "Generate proposal",
          onClick: () =>
            void run("generate", () => codingTaskStage(task.id, "generate")),
        };
      case "generated":
        return {
          label:
            (task.plan?.validation_commands.length ?? 0) > 0
              ? `Run validation (${task.plan?.validation_commands.length} commands)`
              : "Run validation",
          onClick: () =>
            void run("validate", () =>
              validateCodingTask(task.id, task.plan?.validation_commands ?? []),
            ),
        };
      case "validated":
        return {
          label: "Run review",
          onClick: () =>
            void run("review", () => codingTaskStage(task.id, "review")),
        };
      default:
        return null;
    }
  };

  const action = nextAction();
  const canApprove =
    task?.state === "awaiting_approval" && task.review?.ready_for_approval;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4 px-4 py-6">
      {/* Project selection */}
      <div className="flex flex-wrap items-center gap-2">
        <FolderGit2 className="h-4 w-4" style={{ color: "var(--nova)" }} />
        <select
          value={projectId}
          onChange={(event) => setProjectId(event.target.value)}
          disabled={projects.length === 0}
          aria-label="Select project"
          className="min-w-48 rounded-lg border px-2 py-2 text-sm"
          style={{ borderColor: "var(--line)", background: "var(--surface)" }}
        >
          {projects.length === 0 ? (
            <option value="">No projects registered</option>
          ) : (
            projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))
          )}
        </select>
        <button
          onClick={() => setRegistering((value) => !value)}
          className="rounded-lg border px-3 py-2 text-sm"
          style={{ borderColor: "var(--line)" }}
        >
          {registering ? "Cancel" : "Register project"}
        </button>
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {registering && (
        <RegisterProject onSubmit={(data) => void handleRegister(data)} busy={busy === "register"} />
      )}

      {loading ? (
        <div
          className="flex items-center justify-center gap-2.5 py-16 text-sm"
          style={{ color: "var(--dim)" }}
        >
          <NishLogo pulsing />
          Loading projects…
        </div>
      ) : projects.length === 0 && !registering ? (
        <div className="flex flex-col items-center gap-3 py-16 text-center">
          <Code2 className="h-6 w-6" style={{ color: "var(--nova)" }} />
          <p className="text-sm" style={{ color: "var(--dim)" }}>
            Register a project directory to let NISH inspect it and propose
            code changes. NISH never edits a registered project directly —
            every change is prepared in an isolated workspace and shown to
            you as a diff first.
          </p>
        </div>
      ) : (
        projectId && (
          <>
            {/* Project inspection */}
            {scanLoading ? (
              <div
                className="flex items-center gap-2.5 rounded-xl border p-4 text-sm"
                style={{ borderColor: "var(--line)", color: "var(--dim)" }}
              >
                <NishLogo pulsing />
                Inspecting repository…
              </div>
            ) : (
              scan && <ScanPanel scan={scan} />
            )}

            {/* Task input */}
            <div
              className="space-y-2.5 rounded-xl border p-4"
              style={{ borderColor: "var(--line)", background: "var(--surface)" }}
            >
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Describe the coding task, e.g. “Add input validation to the signup form”"
                rows={2}
                maxLength={2000}
                aria-label="Coding task description"
                className="w-full resize-none rounded-lg border bg-transparent px-3 py-2 text-sm outline-none placeholder:text-[var(--dim)]"
                style={{ borderColor: "var(--line)" }}
              />
              <div className="flex items-center justify-between gap-2">
                {tasks.length > 0 && (
                  <select
                    aria-label="Recent tasks"
                    value={task?.id ?? ""}
                    onChange={(event) => {
                      const id = event.target.value;
                      if (!id) return;
                      setDecisionMessage(null);
                      void run("load", () => getCodingTask(id));
                    }}
                    className="max-w-64 rounded-lg border px-2 py-1.5 text-xs"
                    style={{ borderColor: "var(--line)", background: "var(--surface)" }}
                  >
                    <option value="">Recent tasks…</option>
                    {tasks.map((item) => (
                      <option key={item.id} value={item.id}>
                        [{item.state}] {item.description.slice(0, 48)}
                      </option>
                    ))}
                  </select>
                )}
                <button
                  onClick={() => void handleAnalyse()}
                  disabled={description.trim().length < 8 || busy !== null}
                  className="ml-auto flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium disabled:opacity-40"
                  style={{ background: "var(--nova)", color: "var(--bg)" }}
                >
                  <Play className="h-4 w-4" />
                  {busy === "analyse" ? "Analysing…" : "Analyse project"}
                </button>
              </div>
            </div>

            {/* Active task */}
            {task && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Stepper state={task.state} />
                  {busy && busy !== "analyse" && (
                    <span
                      className="flex items-center gap-2 text-xs"
                      style={{ color: "var(--dim)" }}
                    >
                      <NishLogo pulsing />
                      Working…
                    </span>
                  )}
                </div>

                {task.error && (
                  <p
                    className="rounded-lg border px-3 py-2 text-sm"
                    style={{ borderColor: "var(--warn)", color: "var(--warn)" }}
                  >
                    {task.error}
                  </p>
                )}

                {task.plan && <PlanView plan={task.plan} />}

                {action && (
                  <button
                    onClick={action.onClick}
                    className="flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium"
                    style={{ background: "var(--nova)", color: "var(--bg)" }}
                  >
                    <Play className="h-4 w-4" />
                    {action.label}
                  </button>
                )}

                {task.proposal && (
                  <section className="space-y-2">
                    <h3 className="flex items-center gap-2 text-sm font-medium">
                      <Code2 className="h-4 w-4" style={{ color: "var(--nova)" }} />
                      Proposed changes
                      <span
                        className="rounded-full border px-2 py-0.5 text-xs font-normal"
                        style={{ borderColor: "var(--line)", color: "var(--dim)" }}
                      >
                        proposal only — not applied
                      </span>
                    </h3>
                    <p className="text-sm" style={{ color: "var(--dim)" }}>
                      {task.proposal.files.length}{" "}
                      {task.proposal.files.length === 1 ? "file" : "files"}:{" "}
                      {task.proposal.files
                        .map((file) => `${file.path} (${file.change_type})`)
                        .join(", ")}
                    </p>
                    <DiffView diff={task.proposal.diff} />
                  </section>
                )}

                {(task.review || task.validation_runs.length > 0) && (
                  <ReviewView
                    review={task.review}
                    validations={task.validation_runs}
                  />
                )}

                {task.state === "awaiting_approval" && (
                  <div
                    className="space-y-2.5 rounded-xl border p-4"
                    style={{ borderColor: "var(--nova)", background: "var(--surface)" }}
                  >
                    <p className="flex items-center gap-2 text-sm">
                      <ShieldCheck className="h-4 w-4" style={{ color: "var(--nova)" }} />
                      Your decision is recorded only — in this version NISH
                      never merges changes into the live repository. The
                      proposal stays available in the isolated workspace.
                    </p>
                    <div className="flex gap-2">
                      <button
                        onClick={() => void handleDecision("approved")}
                        disabled={!canApprove || busy !== null}
                        title={
                          canApprove
                            ? "Record approval"
                            : "Blocked: review found failing checks or security findings"
                        }
                        className="flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium disabled:opacity-40"
                        style={{ background: "var(--ok)", color: "var(--surface)" }}
                      >
                        <ThumbsUp className="h-4 w-4" />
                        Approve proposal
                      </button>
                      <button
                        onClick={() => void handleDecision("rejected")}
                        disabled={busy !== null}
                        className="flex items-center gap-1.5 rounded-lg border px-3.5 py-2 text-sm"
                        style={{ borderColor: "var(--warn)", color: "var(--warn)" }}
                      >
                        <ThumbsDown className="h-4 w-4" />
                        Reject
                      </button>
                    </div>
                  </div>
                )}

                {decisionMessage && (
                  <p
                    className="rounded-lg border px-3 py-2 text-sm"
                    style={{ borderColor: "var(--ok)", color: "var(--ok)" }}
                    role="status"
                  >
                    {decisionMessage}
                  </p>
                )}
              </div>
            )}
          </>
        )
      )}
    </div>
  );
}
