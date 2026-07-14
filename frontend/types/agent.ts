/**
 * Agent types — mirrors backend/app/agents/models.py.
 * Only the states reachable today are special-cased in the UI, but the
 * full union is typed so later phases don't change these definitions.
 */

export type TaskState =
  | "pending"
  | "planning"
  | "planned"
  | "inspecting"
  | "workspace_ready"
  | "modifying"
  | "testing"
  | "reviewing"
  | "security_review"
  | "awaiting_approval"
  | "merging"
  | "completed"
  | "rejected"
  | "failed"
  | "cancelled";

export type StepKind = "inspect" | "modify" | "test" | "review";

export interface PlanStep {
  id: number;
  title: string;
  kind: StepKind;
  description: string;
  target_files: string[];
}

export interface Plan {
  goal: string;
  assumptions: string[];
  risks: string[];
  steps: PlanStep[];
}

export interface TransitionRecord {
  from_state: TaskState;
  to_state: TaskState;
  at: string;
  note: string;
}

export interface AgentTask {
  id: string;
  description: string;
  state: TaskState;
  granted_capabilities: string[];
  plan: Plan | null;
  error: string | null;
  created_at: string;
  history: TransitionRecord[];
}

export interface TreeEntry {
  path: string;
  size_bytes: number;
}

export interface RepoTree {
  root: string;
  entries: TreeEntry[];
}

export interface AuditVerify {
  ok: boolean;
  message: string;
}
