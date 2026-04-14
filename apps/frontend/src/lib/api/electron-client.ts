/**
 * Electron IPC Client
 * Replaces HTTP fetch() calls with IPC communication
 */

import type {
  StartupSnapshot,
  SkillWorkshopSnapshot,
  ProviderSettingsSnapshot,
  CreateWorkspaceResult,
  ChatResponse,
  SkillUpsertParams,
  JsonObject,
  FileTreeNode,
} from './client';

/**
 * Check if running in Electron environment
 */
export function isElectron(): boolean {
  return typeof window !== 'undefined' && window.electronAPI !== undefined;
}

/**
 * Electron API Client
 * Maps to IPC methods in Main Process
 */
export const electronClient = {
  async getStartup() {
    const result = await window.electronAPI!.invoke('getStartup', {});
    return { startup: result as StartupSnapshot };
  },

  async createWorkspace(params: { novelTitle: string; projectTitle?: string; folderPath?: string }) {
    const result = await window.electronAPI!.invoke('createWorkspace', {
      novel_title: params.novelTitle,
      project_title: params.projectTitle || params.novelTitle,
      folder_path: params.folderPath || '',
    });
    return result as CreateWorkspaceResult;
  },

  async sendChat({
    projectId: _projectId,
    novelId: _novelId,
    params,
  }: {
    projectId: string;
    novelId: string;
    params: {
      session_id?: string;
      project_id: string;
      novel_id: string;
      workbench_type: string;
      user_message: string;
      source_object_id?: string;
      source_revision_id?: string;
    };
  }) {
    const result = await window.electronAPI!.invoke('sendChat', params);
    return result as ChatResponse;
  },

  async getSkills({ projectId, novelId }: { projectId: string; novelId: string }) {
    const result = await window.electronAPI!.invoke('getSkills', {
      project_id: projectId,
      novel_id: novelId,
    });
    return { workshop: result as SkillWorkshopSnapshot };
  },

  async getSettings() {
    const result = await window.electronAPI!.invoke('getSettings', {});
    return { settings: result as ProviderSettingsSnapshot };
  },

  async upsertSkill({
    projectId: _projectId,
    novelId: _novelId,
    params,
  }: {
    projectId: string;
    novelId: string;
    params: SkillUpsertParams;
  }) {
    const result = await window.electronAPI!.invoke('upsertSkill', {
      ...params,
    });
    return result as JsonObject;
  },

  async rollbackSkill({
    projectId: _projectId,
    novelId: _novelId,
    params,
  }: {
    projectId: string;
    novelId: string;
    params: { skill_object_id: string; target_revision_id: string };
  }) {
    const result = await window.electronAPI!.invoke('rollbackSkill', {
      action: 'rollback',
      ...params,
    });
    return result as JsonObject;
  },

  async saveProvider(params: Record<string, unknown>) {
    const result = await window.electronAPI!.invoke('saveProvider', {
      action: 'save',
      ...params,
    });
    return result as JsonObject;
  },

  async activateProvider(providerId: string) {
    const result = await window.electronAPI!.invoke('activateProvider', {
      action: 'activate',
      provider_id: providerId,
    });
    return result as JsonObject;
  },

  async deleteProvider(providerId: string) {
    const result = await window.electronAPI!.invoke('deleteProvider', {
      action: 'delete',
      provider_id: providerId,
    });
    return result as JsonObject;
  },

  async testProvider(providerId: string) {
    const result = await window.electronAPI!.invoke('testProvider', {
      action: 'test',
      provider_id: providerId,
    });
    return result as JsonObject;
  },

  async importSkill({
    projectId: _projectId,
    novelId: _novelId,
    params,
  }: {
    projectId: string;
    novelId: string;
    params: {
      name: string;
      instruction: string;
      description?: string;
      style_scope?: string;
      is_active?: boolean;
      donor_kind?: string;
    };
  }) {
    const result = await window.electronAPI!.invoke('importSkill', {
      action: 'import',
      ...params,
    });
    return result as JsonObject;
  },

  async readDirectory({ projectId, novelId, dirPath }: { projectId: string; novelId: string; dirPath: string }) {
    const result = await window.electronAPI!.invoke('readDirectory', {
      project_id: projectId,
      novel_id: novelId,
      dir_path: dirPath,
    });
    return { tree: (result as { tree: FileTreeNode[] }).tree };
  },

  async readFile({ projectId, novelId, filePath }: { projectId: string; novelId: string; filePath: string }) {
    const result = await window.electronAPI!.invoke('readFile', {
      project_id: projectId,
      novel_id: novelId,
      file_path: filePath,
    });
    return (result as { content: string }).content;
  },
};
