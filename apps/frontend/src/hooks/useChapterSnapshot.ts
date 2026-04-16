/**
 * useChapterSnapshot Hook
 * React hook for managing chapter snapshots
 */

import { useState, useCallback } from 'react';
import { snapshotApi } from '../lib/api/snapshot';
import type { ChapterSnapshot, ConsistencyIssue } from '../types/chapter-snapshot';
import { checkConsistency, compareWithPrevious } from '../lib/consistency-checker';

export interface UseChapterSnapshotReturn {
  snapshot: ChapterSnapshot | null;
  snapshots: ChapterSnapshot[];
  issues: ConsistencyIssue[];
  isLoading: boolean;
  error: string | null;
  load: (projectId: string, chapter: number) => Promise<void>;
  save: (projectId: string, snapshot: ChapterSnapshot) => Promise<void>;
  extractAndSave: (projectId: string, chapter: number, content: string) => Promise<void>;
  runConsistencyCheck: (manifest: unknown) => void;
  clearError: () => void;
}

export function useChapterSnapshot(_projectId: string, chapterNumber: number): UseChapterSnapshotReturn {
  const [snapshot, setSnapshot] = useState<ChapterSnapshot | null>(null);
  const [snapshots, setSnapshots] = useState<ChapterSnapshot[]>([]);
  const [issues, setIssues] = useState<ConsistencyIssue[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const load = useCallback(async (projId: string, chapter: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await snapshotApi.load(projId, chapter);
      setSnapshot(result);

      // Also load all snapshots for comparison
      const allSnapshots = await snapshotApi.getAll(projId);
      setSnapshots(allSnapshots);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load snapshot');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const save = useCallback(async (projId: string, snap: ChapterSnapshot) => {
    setIsLoading(true);
    setError(null);
    try {
      await snapshotApi.save(projId, snap);
      setSnapshot(snap);

      // Update snapshots list
      const allSnapshots = await snapshotApi.getAll(projId);
      setSnapshots(allSnapshots);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save snapshot');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const extractAndSave = useCallback(async (projId: string, chapter: number, content: string) => {
    setIsLoading(true);
    setError(null);
    try {
      // Extract content from chapter text
      const extracted = await snapshotApi.extract(projId, chapter, content);

      // Get previous snapshot for comparison
      const previousSnapshot = chapter > 1 ? await snapshotApi.load(projId, chapter - 1) : null;

      // Build character states from extracted data
      const characterStates = (extracted?.characters || []).map((name, index) => ({
        characterId: `char_${index}`,
        name,
        location: extracted?.locations?.[0] || '',
        emotionalState: 'unknown',
        status: 'unknown' as const,
        recentEvents: [],
      }));

      // Build world state from extracted data
      const worldState = {
        currentTimeline: extracted?.timeMarkers?.[0] || '',
        activeConflicts: [] as string[],
        revealedSecrets: [] as string[],
        pendingMysteries: 0,
      };

      const newSnapshot: ChapterSnapshot = {
        chapterNumber: chapter,
        characterStates,
        worldState,
        timestamp: new Date().toISOString(),
      };

      // Run comparison with previous
      const comparisonIssues = compareWithPrevious(newSnapshot, previousSnapshot);
      setIssues(prev => [...prev, ...comparisonIssues]);

      // Save the snapshot
      await snapshotApi.save(projId, newSnapshot);
      setSnapshot(newSnapshot);

      // Refresh snapshots list
      const allSnapshots = await snapshotApi.getAll(projId);
      setSnapshots(allSnapshots);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to extract and save');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const runConsistencyCheck = useCallback((manifest: unknown) => {
    if (!snapshot) return;

    const consistencyIssues = checkConsistency(chapterNumber, snapshot, manifest as Parameters<typeof checkConsistency>[2]);
    setIssues(prev => [...prev, ...consistencyIssues]);
  }, [snapshot, chapterNumber]);

  return {
    snapshot,
    snapshots,
    issues,
    isLoading,
    error,
    load,
    save,
    extractAndSave,
    runConsistencyCheck,
    clearError,
  };
}
