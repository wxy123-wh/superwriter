type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = Record<string, JsonValue>;

interface ApiSuccessEnvelope<T> {
  ok: true;
  data: T;
}

export interface WorkspaceContextSnapshot {
  project_id: string;
  project_title: string;
  novel_id: string | null;
  novel_title: string | null;
}

export interface StartupSnapshot {
  workspace_contexts: WorkspaceContextSnapshot[];
  has_workspace_contexts: boolean;
}

export interface WorkspaceObjectSummary {
  family: string;
  object_id: string;
  current_revision_id: string;
  current_revision_number: number;
  payload: JsonObject;
}

export interface ChatResponse {
  session_id: string;
  user_message_state_id: string;
  assistant_message_state_id: string;
  assistant_content: string;
}

export interface SendChatParams {
  session_id?: string;
  project_id: string;
  novel_id: string;
  workbench_type: string;
  user_message: string;
  source_object_id?: string;
  source_revision_id?: string;
}

export interface ImportSkillParams {
  name: string;
  instruction: string;
  description?: string;
  style_scope?: string;
  is_active?: boolean;
  donor_kind?: string;
}

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
  payload: JsonObject;
}

export interface SkillWorkshopVersionSnapshot {
  revision_id: string;
  revision_number: number;
  parent_revision_id: string | null;
  name: string;
  instruction: string;
  style_scope: string;
  is_active: boolean;
  payload: JsonObject;
}

export interface SkillWorkshopComparison {
  skill_object_id: string;
  left_revision_id: string;
  left_revision_number: number;
  right_revision_id: string;
  right_revision_number: number;
  structured_diff: JsonObject;
  rendered_diff: string;
}

export interface SkillWorkshopSnapshot {
  project_id: string;
  novel_id: string;
  skills: SkillWorkshopSkillSnapshot[];
  selected_skill: SkillWorkshopSkillSnapshot | null;
  versions: SkillWorkshopVersionSnapshot[];
  comparison: SkillWorkshopComparison | null;
}

export type SkillUpsertParams =
  | {
      action: 'create';
      name: string;
      instruction: string;
      description?: string;
      style_scope?: string;
      is_active?: boolean;
    }
  | {
      action: 'update';
      skill_object_id: string;
      name?: string;
      description?: string;
      instruction?: string;
      style_scope?: string;
      is_active?: boolean;
      base_revision_id?: string;
    };

export interface ProviderSettingsSnapshot {
  providers: JsonObject[];
  active_provider: JsonObject | null;
}

export interface FileTreeNode {
  name: string;
  path: string;
  kind: 'file' | 'directory';
  children?: FileTreeNode[];
}

export class ApiContractError extends Error {
  constructor(
    public readonly endpoint: string,
    message: string,
    public readonly payload?: unknown,
  ) {
    super(message);
    this.name = 'ApiContractError';
  }
}

export class ApiResponseError extends Error {
  constructor(
    public readonly endpoint: string,
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details: JsonObject,
  ) {
    super(message);
    this.name = 'ApiResponseError';
  }
}

function assertRecord(value: unknown, context: string): asserts value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${context} must be an object`);
  }
}

function expectString(value: unknown, context: string): string {
  if (typeof value !== 'string') {
    throw new Error(`${context} must be a string`);
  }
  return value;
}

function expectNullableString(value: unknown, context: string): string | null {
  if (value === null) {
    return null;
  }
  return expectString(value, context);
}

function expectBoolean(value: unknown, context: string): boolean {
  if (typeof value !== 'boolean') {
    throw new Error(`${context} must be a boolean`);
  }
  return value;
}

function expectNumber(value: unknown, context: string): number {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    throw new Error(`${context} must be a number`);
  }
  return value;
}

function expectJsonObject(value: unknown, context: string): JsonObject {
  assertRecord(value, context);
  return value as JsonObject;
}

function expectArray<T>(value: unknown, context: string, parser: (item: unknown, context: string) => T): T[] {
  if (!Array.isArray(value)) {
    throw new Error(`${context} must be an array`);
  }
  return value.map((item, index) => parser(item, `${context}[${index}]`));
}

function parseWorkspaceContext(value: unknown, context: string): WorkspaceContextSnapshot {
  assertRecord(value, context);
  return {
    project_id: expectString(value.project_id, `${context}.project_id`),
    project_title: expectString(value.project_title, `${context}.project_title`),
    novel_id: expectNullableString(value.novel_id, `${context}.novel_id`),
    novel_title: expectNullableString(value.novel_title, `${context}.novel_title`),
  };
}

function parseSkillWorkshopSkill(value: unknown, context: string): SkillWorkshopSkillSnapshot {
  assertRecord(value, context);
  return {
    object_id: expectString(value.object_id, `${context}.object_id`),
    revision_id: expectString(value.revision_id, `${context}.revision_id`),
    revision_number: expectNumber(value.revision_number, `${context}.revision_number`),
    name: expectString(value.name, `${context}.name`),
    description: expectString(value.description, `${context}.description`),
    instruction: expectString(value.instruction, `${context}.instruction`),
    style_scope: expectString(value.style_scope, `${context}.style_scope`),
    is_active: expectBoolean(value.is_active, `${context}.is_active`),
    source_kind: expectString(value.source_kind, `${context}.source_kind`),
    donor_kind: expectNullableString(value.donor_kind, `${context}.donor_kind`),
    payload: expectJsonObject(value.payload, `${context}.payload`),
  };
}

function parseSkillWorkshopVersion(value: unknown, context: string): SkillWorkshopVersionSnapshot {
  assertRecord(value, context);
  return {
    revision_id: expectString(value.revision_id, `${context}.revision_id`),
    revision_number: expectNumber(value.revision_number, `${context}.revision_number`),
    parent_revision_id: expectNullableString(value.parent_revision_id, `${context}.parent_revision_id`),
    name: expectString(value.name, `${context}.name`),
    instruction: expectString(value.instruction, `${context}.instruction`),
    style_scope: expectString(value.style_scope, `${context}.style_scope`),
    is_active: expectBoolean(value.is_active, `${context}.is_active`),
    payload: expectJsonObject(value.payload, `${context}.payload`),
  };
}

function parseSkillWorkshopComparison(value: unknown, context: string): SkillWorkshopComparison {
  assertRecord(value, context);
  return {
    skill_object_id: expectString(value.skill_object_id, `${context}.skill_object_id`),
    left_revision_id: expectString(value.left_revision_id, `${context}.left_revision_id`),
    left_revision_number: expectNumber(value.left_revision_number, `${context}.left_revision_number`),
    right_revision_id: expectString(value.right_revision_id, `${context}.right_revision_id`),
    right_revision_number: expectNumber(value.right_revision_number, `${context}.right_revision_number`),
    structured_diff: expectJsonObject(value.structured_diff, `${context}.structured_diff`),
    rendered_diff: expectString(value.rendered_diff, `${context}.rendered_diff`),
  };
}

function parseStartupSnapshot(value: unknown): StartupSnapshot {
  assertRecord(value, 'startup');
  return {
    workspace_contexts: expectArray(value.workspace_contexts, 'startup.workspace_contexts', parseWorkspaceContext),
    has_workspace_contexts: expectBoolean(value.has_workspace_contexts, 'startup.has_workspace_contexts'),
  };
}

function parseSkillWorkshopSnapshot(value: unknown): SkillWorkshopSnapshot {
  assertRecord(value, 'workshop');
  return {
    project_id: expectString(value.project_id, 'workshop.project_id'),
    novel_id: expectString(value.novel_id, 'workshop.novel_id'),
    skills: expectArray(value.skills, 'workshop.skills', parseSkillWorkshopSkill),
    selected_skill: value.selected_skill === null ? null : parseSkillWorkshopSkill(value.selected_skill, 'workshop.selected_skill'),
    versions: expectArray(value.versions, 'workshop.versions', parseSkillWorkshopVersion),
    comparison: value.comparison === null ? null : parseSkillWorkshopComparison(value.comparison, 'workshop.comparison'),
  };
}

function parseProviderSettingsSnapshot(value: unknown): ProviderSettingsSnapshot {
  assertRecord(value, 'settings');
  return {
    providers: expectArray(value.providers, 'settings.providers', expectJsonObject),
    active_provider: value.active_provider === null ? null : expectJsonObject(value.active_provider, 'settings.active_provider'),
  };
}

function parseApiError(value: unknown, endpoint: string, status: number): ApiResponseError {
  assertRecord(value, endpoint);
  assertRecord(value.error, `${endpoint}.error`);

  return new ApiResponseError(
    endpoint,
    status,
    expectString(value.error.code, `${endpoint}.error.code`),
    expectString(value.error.message, `${endpoint}.error.message`),
    expectJsonObject(value.error.details, `${endpoint}.error.details`),
  );
}

function buildUrl(path: string, search?: Record<string, string | null | undefined>): string {
  const params = new URLSearchParams();

  for (const [key, value] of Object.entries(search ?? {})) {
    if (value) {
      params.set(key, value);
    }
  }

  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

async function parseEnvelope<T>(
  endpoint: string,
  response: Response,
  parser: (payload: unknown) => T,
): Promise<ApiSuccessEnvelope<T>> {
  let rawPayload: unknown;

  try {
    rawPayload = await response.json();
  } catch (error) {
    throw new ApiContractError(endpoint, `Expected JSON from ${endpoint}`, error);
  }

  try {
    assertRecord(rawPayload, endpoint);

    if (rawPayload.ok === true) {
      assertRecord(rawPayload.data, `${endpoint}.data`);
      return {
        ok: true,
        data: parser(rawPayload.data),
      };
    }

    if (rawPayload.ok === false) {
      throw parseApiError(rawPayload, endpoint, response.status);
    }

    throw new Error(`${endpoint}.ok must be a boolean discriminator`);
  } catch (error) {
    if (error instanceof ApiResponseError) {
      throw error;
    }

    throw new ApiContractError(
      endpoint,
      error instanceof Error ? error.message : `Unexpected API contract failure at ${endpoint}`,
      rawPayload,
    );
  }
}

async function request<T>(
  path: string,
  parser: (payload: unknown) => T,
  search?: Record<string, string | null | undefined>,
): Promise<T> {
  const endpoint = buildUrl(path, search);
  const response = await fetch(endpoint, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  const envelope = await parseEnvelope(endpoint, response, parser);
  return envelope.data;
}

async function mutate<T>(
  path: string,
  body: unknown,
  parser: (payload: unknown) => T,
  method: 'POST' | 'PUT' | 'DELETE' = 'POST',
  search?: Record<string, string | null | undefined>,
): Promise<T> {
  const endpoint = buildUrl(path, search);
  const response = await fetch(endpoint, {
    method,
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  const envelope = await parseEnvelope(endpoint, response, parser);
  return envelope.data;
}

export interface CreateWorkspaceResult {
  project_id: string;
  novel_id: string;
  manifest_path: string;
}

// Conditional import: use Electron IPC if available, otherwise use HTTP
import { electronClient, isElectron } from './electron-client';

export const apiClient = {
  getStartup() {
    if (isElectron()) {
      return electronClient.getStartup();
    }
    return request('/api/startup', (payload) => ({ startup: parseStartupSnapshot(expectJsonObject(payload, 'startup data').startup) }));
  },
  createWorkspace(params: { novelTitle: string; projectTitle?: string; folderPath?: string }) {
    if (isElectron()) {
      return electronClient.createWorkspace(params);
    }
    return mutate<CreateWorkspaceResult>(
      '/api/create-novel',
      {
        novel_title: params.novelTitle,
        project_title: params.projectTitle || params.novelTitle,
        folder_path: params.folderPath || '',
      },
      (payload) => {
        assertRecord(payload, 'workspace');
        return {
          project_id: expectString(payload.project_id, 'workspace.project_id'),
          novel_id: expectString(payload.novel_id, 'workspace.novel_id'),
          manifest_path: expectString(payload.manifest_path, 'workspace.manifest_path'),
        };
      },
    );
  },
  sendChat({
    projectId,
    novelId,
    params,
  }: {
    projectId: string;
    novelId: string;
    params: SendChatParams;
  }) {
    if (isElectron()) {
      return electronClient.sendChat({ projectId, novelId, params });
    }
    return mutate<ChatResponse>(
      '/api/chat',
      params,
      (payload) => {
        assertRecord(payload, 'chat result');
        return {
          session_id: expectString(payload.session_id, 'session_id'),
          user_message_state_id: expectString(payload.user_message_state_id, 'user_message_state_id'),
          assistant_message_state_id: expectString(payload.assistant_message_state_id, 'assistant_message_state_id'),
          assistant_content: expectString(payload.assistant_content, 'assistant_content'),
        };
      },
      undefined,
      { project_id: projectId, novel_id: novelId },
    );
  },
  getSkills({ projectId, novelId }: { projectId: string; novelId: string }) {
    return request(
      '/api/skills',
      (payload) => ({ workshop: parseSkillWorkshopSnapshot(expectJsonObject(payload, 'skills data').workshop) }),
      { project_id: projectId, novel_id: novelId },
    );
  },
  getSettings() {
    return request('/api/settings', (payload) => ({ settings: parseProviderSettingsSnapshot(expectJsonObject(payload, 'settings data').settings) }));
  },
  upsertSkill({
    projectId,
    novelId,
    params,
  }: {
    projectId: string;
    novelId: string;
    params: SkillUpsertParams;
  }) {
    return mutate('/api/skills', params, (payload) => {
      assertRecord(payload, 'result');
      return payload;
    }, undefined, { project_id: projectId, novel_id: novelId });
  },
  rollbackSkill({
    projectId,
    novelId,
    params,
  }: {
    projectId: string;
    novelId: string;
    params: { skill_object_id: string; target_revision_id: string };
  }) {
    return mutate('/api/skills', { action: 'rollback', ...params }, (payload) => {
      assertRecord(payload, 'result');
      return payload;
    }, undefined, { project_id: projectId, novel_id: novelId });
  },
  saveProvider(params: Record<string, unknown>) {
    if (isElectron()) {
      return electronClient.saveProvider(params);
    }
    return mutate('/api/settings', { action: 'save', ...params }, (payload) => {
      assertRecord(payload, 'result');
      return payload;
    });
  },
  activateProvider(providerId: string) {
    if (isElectron()) {
      return electronClient.activateProvider(providerId);
    }
    return mutate('/api/settings', { action: 'activate', provider_id: providerId }, (payload) => {
      assertRecord(payload, 'result');
      return payload;
    });
  },
  deleteProvider(providerId: string) {
    if (isElectron()) {
      return electronClient.deleteProvider(providerId);
    }
    return mutate('/api/settings', { action: 'delete', provider_id: providerId }, (payload) => {
      assertRecord(payload, 'result');
      return payload;
    });
  },
  testProvider(providerId: string) {
    if (isElectron()) {
      return electronClient.testProvider(providerId);
    }
    return mutate('/api/settings', { action: 'test', provider_id: providerId }, (payload) => {
      assertRecord(payload, 'result');
      return payload as Record<string, unknown>;
    });
  },
  importSkill({
    projectId,
    novelId,
    params,
  }: {
    projectId: string;
    novelId: string;
    params: ImportSkillParams;
  }) {
    return mutate('/api/skills', { action: 'import', ...params }, (payload) => {
      assertRecord(payload, 'result');
      return payload;
    }, undefined, { project_id: projectId, novel_id: novelId });
  },
  openChatSession({
    projectId,
    novelId,
    params,
  }: {
    projectId: string;
    novelId: string;
    params?: { title?: string; runtime_origin?: string; source_ref?: string };
  }) {
    return mutate(
      '/api/chat-sessions',
      params ?? {},
      (payload) => {
        assertRecord(payload, 'chat session');
        return { session: expectJsonObject(payload.session, 'chat-sessions.session') };
      },
      undefined,
      { project_id: projectId, novel_id: novelId },
    );
  },
  getChatSession({ projectId, novelId, sessionId }: { projectId: string; novelId: string; sessionId: string }) {
    return request(
      '/api/chat-sessions',
      (payload) => {
        assertRecord(payload, 'chat session');
        return { session: expectJsonObject(payload.session, 'chat-sessions.session') };
      },
      { project_id: projectId, novel_id: novelId, session_id: sessionId },
    );
  },
  readDirectory({ projectId, novelId, dirPath }: { projectId: string; novelId: string; dirPath: string }) {
    return request(
      '/api/workspace/read-directory',
      (payload) => {
        assertRecord(payload, 'read-directory result');
        const tree = (value: unknown) => parseFileTreeNode(value, 'tree');
        return { tree: expectArray(payload.tree ?? [], 'read-directory.tree', tree) };
      },
      { project_id: projectId, novel_id: novelId, dir_path: dirPath },
    );
  },
  readFile({ projectId, novelId, filePath }: { projectId: string; novelId: string; filePath: string }) {
    return request(
      '/api/workspace/read-file',
      (payload) => {
        assertRecord(payload, 'read-file result');
        return { content: expectString(payload.content, 'read-file.content') };
      },
      { project_id: projectId, novel_id: novelId, file_path: filePath },
    );
  },
};

function parseFileTreeNode(value: unknown, context: string): FileTreeNode {
  assertRecord(value, context);
  return {
    name: expectString(value.name, `${context}.name`),
    path: expectString(value.path, `${context}.path`),
    kind: (value.kind === 'directory' ? 'directory' : 'file') as 'file' | 'directory',
    children: value.children
      ? expectArray(value.children, `${context}.children`, parseFileTreeNode)
      : undefined,
  };
}
