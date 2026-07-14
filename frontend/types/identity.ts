/** Mirrors GET /api/identity (backend/app/api/identity.py). */

export interface IdentityInfo {
  name: string;
  tagline: string;
  creator: string;
  lead_developer: string;
  project_started: number;
  company: string;
  version: string;
  purpose: string;
  personality_style: string;
  principles: string[];
  current_model: string;
  model_runtime: string;
}
