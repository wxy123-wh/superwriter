/**
 * Snapshot API Client
 * Provides IPC-based access to chapter snapshot operations
 */

import type { ChapterSnapshot, ExtractedContent } from '../../types/chapter-snapshot';

interface LoadSnapshotResult { snapshot: ChapterSnapshot | null; error?: string }
interface SaveSnapshotResult { success: boolean; error?: string }
interface GetAllSnapshotsResult { snapshots: ChapterSnapshot[]; error?: string }
interface ExtractContentResult { extracted: ExtractedContent | null; error?: string }

export const snapshotApi = {
  /**
   * Load a specific chapter snapshot
   */
  async load(projectId: string, chapter: number): Promise<ChapterSnapshot | null> {
    if (typeof window === 'undefined' || !window.electronAPI) return null;
    const result = await window.electronAPI.invoke('loadChapterSnapshot', { projectId, chapter }) as LoadSnapshotResult;
    return result.snapshot;
  },

  /**
   * Save a chapter snapshot
   */
  async save(projectId: string, snapshot: ChapterSnapshot): Promise<boolean> {
    if (typeof window === 'undefined' || !window.electronAPI) return false;
    const result = await window.electronAPI.invoke('saveChapterSnapshot', { projectId, snapshot }) as SaveSnapshotResult;
    return result.success;
  },

  /**
   * Get all snapshots for a project
   */
  async getAll(projectId: string): Promise<ChapterSnapshot[]> {
    if (typeof window === 'undefined' || !window.electronAPI) return [];
    const result = await window.electronAPI.invoke('getAllSnapshots', { projectId }) as GetAllSnapshotsResult;
    return result.snapshots || [];
  },

  /**
   * Extract content from chapter text
   */
  async extract(projectId: string, chapter: number, content: string): Promise<ExtractedContent | null> {
    if (typeof window === 'undefined' || !window.electronAPI) return null;
    const result = await window.electronAPI.invoke('extractChapterContent', { projectId, chapter, content }) as ExtractContentResult;
    return result.extracted;
  },
};
