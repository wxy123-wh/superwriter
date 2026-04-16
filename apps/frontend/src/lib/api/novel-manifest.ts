import type { NovelManifest } from '../../types/novel-manifest';

export const novelManifestApi = {
  async ensureDir(projectId: string): Promise<{ success: boolean; error?: string }> {
    const result = await window.electronAPI?.invoke('ensureManifestDir', { projectId });
    return result as { success: boolean; error?: string };
  },

  async load(projectId: string): Promise<{ manifest: NovelManifest | null; error?: string }> {
    const result = await window.electronAPI?.invoke('loadNovelManifest', { projectId });
    return result as { manifest: NovelManifest | null; error?: string };
  },

  async save(projectId: string, manifest: NovelManifest): Promise<{ success: boolean; error?: string }> {
    const result = await window.electronAPI?.invoke('saveNovelManifest', { projectId, manifest });
    return result as { success: boolean; error?: string };
  },
};
