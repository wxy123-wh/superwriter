import type { JSONObject } from "./json.js";

// ─── Skill Workshop Snapshots ────────────────────────────────────────────────

export interface SkillWorkshopSkillSnapshot {
  object_id: string;
  revision_id: string;
  revision_number: number;
  name: string;
  description: string;
  instruction: string;
  style_scope: string;
  is_active: boolean;
  source_kind: string;
  donor_kind: string | null;
  payload: JSONObject;
}

export interface SkillWorkshopVersionSnapshot {
  revision_id: string;
  revision_number: number;
  parent_revision_id: string | null;
  name: string;
  instruction: string;
  style_scope: string;
  is_active: boolean;
  payload: JSONObject;
}

// ─── Skill Workshop Requests ─────────────────────────────────────────────────

export interface SkillWorkshopRequest {
  project_id: string;
  novel_id?: string;
  selected_skill_id?: string;
  left_revision_id?: string;
  right_revision_id?: string;
}

export interface SkillWorkshopCompareRequest {
  skill_object_id: string;
  left_revision_id: string;
  right_revision_id: string;
}

export interface SkillWorkshopUpsertRequest {
  project_id: string;
  novel_id?: string;
  actor: string;
  source_surface?: string;
  skill_object_id?: string;
  name: string;
  description?: string;
  instruction: string;
  style_scope?: string;
  is_active?: boolean;
  base_revision_id?: string;
  revision_reason?: string;
  source_ref?: string;
  import_mapping?: JSONObject;
  source_kind?: string;
}

export interface SkillWorkshopImportRequest {
  project_id: string;
  novel_id?: string;
  actor: string;
  source_surface?: string;
  donor_kind: string;
  donor_payload: JSONObject;
  name: string;
  description?: string;
  instruction: string;
  style_scope?: string;
  is_active?: boolean;
  source_ref?: string;
}

export interface SkillWorkshopRollbackRequest {
  skill_object_id: string;
  target_revision_id: string;
  actor: string;
  source_surface?: string;
  revision_reason?: string;
}

// ─── Skill Workshop Results ───────────────────────────────────────────────────

export interface SkillWorkshopComparison {
  skill_object_id: string;
  left_revision_id: string;
  left_revision_number: number;
  right_revision_id: string;
  right_revision_number: number;
  structured_diff: JSONObject;
  rendered_diff: string;
}

export interface SkillWorkshopMutationResult {
  object_id: string;
  revision_id: string;
  revision_number: number;
  disposition: string;
  policy_class: string;
  payload: JSONObject;
}

export interface SkillWorkshopResult {
  project_id: string;
  novel_id: string;
  skills: SkillWorkshopSkillSnapshot[];
  selected_skill: SkillWorkshopSkillSnapshot | null;
  versions: SkillWorkshopVersionSnapshot[];
  comparison: SkillWorkshopComparison | null;
}

// ─── Skill Execution ──────────────────────────────────────────────────────────

export interface SkillExecutionRequest {
  skill_name: string;
  actor: string;
  source_surface?: string;
  mutation_request?: unknown;
  export_request?: unknown;
}

export interface SkillExecutionResult {
  skill_name: string;
  mutation_result: unknown;
  export_result: unknown;
}
