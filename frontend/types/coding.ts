/** Mirrors backend/app/schemas/coding.py. */

export interface CodingProject {
  id: string;
  name: string;
  root_path: string;
  description: string;
  default_branch: string;
  created_at: string;
  updated_at: string;
  last_scanned_at: string | null;
}

export interface ProjectScan {
  files: { path: string; size_bytes: number }[];
  technologies: string[];
  readme_excerpt: string;
  dependency_files: string[];
  test_commands: string[];
  git_branch: string | null;
  git_dirty_files: number | null;
}

export interface CodingPlan {
  task_summary: string;
  assumptions: string[];
  files_to_inspect: string[];
  files_to_modify: string[];
  files_to_create: string[];
  steps: string[];
  validation_commands: string[];
  risks: string[];
  approval_requirements: string[];
}

export interface ValidationRun {
  command: string;
  exit_code: number | null;
  duration_ms: number;
  passed: boolean;
  timed_out: boolean;
  output_excerpt: string;
}

export interface ReviewFinding {
  severity: "high" | "warning";
  path: string;
  message: string;
}

export interface Review {
  findings: ReviewFinding[];
  notes: string[];
  tests_ran: boolean;
  tests_passed: boolean;
  ready_for_approval: boolean;
}

export interface Proposal {
  id: string;
  status: "proposed" | "approved" | "rejected";
  summary: string;
  diff: string;
  files: { path: string; change_type: "modify" | "create" }[];
  warnings: string[];
  created_at: string;
}

export type CodingTaskState =
  | "created" | "planning" | "planned" | "workspace_ready" | "generating"
  | "generated" | "validating" | "validated" | "awaiting_approval"
  | "approved" | "rejected" | "failed";

export interface Approval {
  decision: "approved" | "rejected";
  note: string;
  /** sha256 binding the approval to the exact reviewed change set. */
  proposal_hash: string | null;
  expires_at: string | null;
  decided_at: string;
}

export type ApplicationStatus =
  | "applying"
  | "validation_failed"
  | "failed"
  | "committed"
  | "rolled_back";

export interface ChangeApplication {
  id: string;
  status: ApplicationStatus;
  branch_name: string;
  original_branch: string;
  original_head: string;
  commit_hash: string | null;
  final_diff: string;
  error: string | null;
  created_at: string;
  rolled_back_at: string | null;
}

export interface CodingTask {
  id: string;
  project_id: string;
  description: string;
  state: CodingTaskState;
  plan: CodingPlan | null;
  error: string | null;
  created_at: string;
  proposal: Proposal | null;
  validation_runs: ValidationRun[];
  review: Review | null;
  approval: Approval | null;
  application: ChangeApplication | null;
}
