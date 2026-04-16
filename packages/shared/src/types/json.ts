// Shared JSON value types — single source of truth for the entire repo

export type JSONScalar = string | number | boolean | null;
export type JSONValue = JSONScalar | JSONValue[] | JSONObject;
export interface JSONObject {
  [key: string]: JSONValue;
}
