import type { JSONObject } from "./json.js";

// Workbench types for the outline→plot→event→scene→chapter pipeline.
// These are stubs — canonical storage is not yet implemented.

export interface ChapterMutationSignals {
  signals: JSONObject;
}

export interface WorkbenchDisposition {
  disposition: "generated" | "review_required" | "applied";
  child_object_id?: string;
  child_revision_id?: string;
  proposal_id?: string;
  review_route?: string;
  plot_payload?: JSONObject;
  delta_payload?: JSONObject;
  lineage_payload?: JSONObject;
  reasons?: string[];
  additional_plot_ids?: string[];
}

export interface OutlineToPlotWorkbenchRequest {
  project_id: string;
  novel_id?: string;
  outline_node_object_id: string;
  actor: string;
  expected_parent_revision_id?: string;
  target_child_object_id?: string;
  base_child_revision_id?: string;
  require_ai?: boolean;
}

export interface OutlineToPlotWorkbenchResult extends WorkbenchDisposition {}

export interface PlotToEventWorkbenchRequest {
  project_id: string;
  novel_id?: string;
  plot_node_object_id: string;
  actor: string;
  expected_parent_revision_id?: string;
  target_child_object_id?: string;
  base_child_revision_id?: string;
  require_ai?: boolean;
}

export interface PlotToEventWorkbenchResult extends WorkbenchDisposition {}

export interface EventToSceneWorkbenchRequest {
  project_id: string;
  novel_id?: string;
  event_object_id: string;
  actor: string;
  expected_parent_revision_id?: string;
  target_child_object_id?: string;
  base_child_revision_id?: string;
  require_ai?: boolean;
}

export interface EventToSceneWorkbenchResult extends WorkbenchDisposition {}

export interface SceneToChapterWorkbenchRequest {
  project_id: string;
  novel_id?: string;
  scene_object_id: string;
  chapter_signals?: ChapterMutationSignals;
  skill_name?: string;
  actor: string;
}

export interface SceneToChapterWorkbenchResult extends WorkbenchDisposition {
  artifact_object_id?: string;
  artifact_revision_id?: string;
  chapter_payload?: JSONObject;
  style_rules?: unknown[];
  scoped_skills?: unknown[];
  canonical_facts?: unknown[];
}
