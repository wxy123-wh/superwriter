import type { JSONObject } from "./json.js";

// ─── Chat Messages ────────────────────────────────────────────────────────────

export interface ChatMessageRequest {
  chat_message_id: string;
  chat_role: string;
  payload: JSONObject;
}

export interface ChatMessageSnapshot {
  message_state_id: string;
  chat_message_id: string;
  chat_role: string;
  linked_object_id: string | null;
  linked_revision_id: string | null;
  payload: JSONObject;
}

export interface ChatSessionSnapshot {
  session_id: string;
  project_id: string;
  novel_id: string | null;
  title: string | null;
  runtime_origin: string;
  created_by: string;
  messages: ChatMessageSnapshot[];
}

// ─── Chat Requests / Results ──────────────────────────────────────────────────

export interface OpenChatSessionRequest {
  project_id: string;
  created_by: string;
  runtime_origin: string;
  novel_id?: string;
  title?: string;
  source_ref?: string;
}

export interface OpenChatSessionResult {
  session_id: string;
  project_id: string;
  created_by: string;
  runtime_origin: string;
  novel_id: string | null;
  title: string | null;
  source_ref: string | null;
}

export interface GetChatSessionRequest {
  session_id: string;
}

export interface ChatTurnRequest {
  session_id?: string;
  project_id: string;
  novel_id?: string;
  title?: string;
  workbench_type?: string;
  user_message: ChatMessageRequest;
  assistant_message: ChatMessageRequest;
  source_object_id?: string;
  source_revision_id?: string;
  mutation_requests?: unknown[];
  export_requests?: unknown[];
  skill_requests?: unknown[];
}

export interface ChatTurnResult {
  session_id: string;
  user_message_state_id: string;
  assistant_message_state_id: string;
  assistant_content: string;
  mutation_results?: unknown[];
  export_results?: unknown[];
  skill_results?: unknown[];
}
