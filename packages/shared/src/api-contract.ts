import type { JSONObject } from "./types/json.js";

// ─── API Envelope ────────────────────────────────────────────────────────────

export interface ApiEnvelope<T> {
  ok: true;
  data: T;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  details: JSONObject;
}

export interface ApiErrorEnvelope {
  ok: false;
  error: ApiErrorDetail;
}

export function apiOk<T>(data: T): ApiEnvelope<T> {
  return { ok: true, data };
}

export function apiErr(code: string, message: string, details: JSONObject = {}): ApiErrorEnvelope {
  return { ok: false, error: { code, message, details } };
}
