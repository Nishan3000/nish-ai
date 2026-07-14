/** Mirrors backend/app/schemas/memories.py. */

export type MemoryType =
  | "user_preference"
  | "personal_fact"
  | "project_fact"
  | "goal"
  | "correction"
  | "successful_outcome"
  | "failed_outcome"
  | "custom";

export const MEMORY_TYPES: MemoryType[] = [
  "user_preference",
  "personal_fact",
  "project_fact",
  "goal",
  "correction",
  "successful_outcome",
  "failed_outcome",
  "custom",
];

export const MEMORY_TYPE_LABELS: Record<MemoryType, string> = {
  user_preference: "Preference",
  personal_fact: "Personal fact",
  project_fact: "Project fact",
  goal: "Goal",
  correction: "Correction",
  successful_outcome: "Worked well",
  failed_outcome: "Didn't work",
  custom: "Custom",
};

export interface Memory {
  id: string;
  memory_type: MemoryType;
  content: string;
  source: string;
  importance_score: number;
  is_active: boolean;
  project_id: string | null;
  created_at: string;
  updated_at: string;
}

/** Compact form attached to chat responses. */
export interface MemoryUsed {
  id: string;
  memory_type: string;
  content: string;
}
