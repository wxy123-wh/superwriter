import { useState, useCallback, useEffect } from 'react';
import type { Foreshadow, ForeshadowStatus, ForeshadowImportance } from '../types/foreshadow';
import { foreshadowApi } from '../lib/api/foreshadow';

export interface UseForeshadowsReturn {
  foreshadows: Foreshadow[];
  add: (data: {
    title: string;
    description: string;
    importance: ForeshadowImportance;
    plantedChapter: number;
    keywords: string[];
  }) => Promise<void>;
  resolve: (id: string, chapter: number) => Promise<void>;
  abandon: (id: string) => Promise<void>;
  update: (id: string, updates: Partial<Foreshadow>) => Promise<void>;
  remove: (id: string) => Promise<void>;
  isLoading: boolean;
  error: string | null;
}

export function useForeshadows(projectId: string): UseForeshadowsReturn {
  const [foreshadows, setForeshadows] = useState<Foreshadow[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await foreshadowApi.load(projectId);
      setForeshadows(result.foreshadows || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load foreshadows');
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  const save = useCallback(async (items: Foreshadow[]) => {
    if (!projectId) return;
    try {
      await foreshadowApi.save(projectId, items);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save foreshadows');
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const add = useCallback(async (data: {
    title: string;
    description: string;
    importance: ForeshadowImportance;
    plantedChapter: number;
    keywords: string[];
  }) => {
    const now = new Date().toISOString();
    const newForeshadow: Foreshadow = {
      id: `fs_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
      title: data.title,
      description: data.description,
      status: 'pending',
      importance: data.importance,
      plantedChapter: data.plantedChapter,
      keywords: data.keywords,
      createdAt: now,
      updatedAt: now,
    };
    const updated = [...foreshadows, newForeshadow];
    setForeshadows(updated);
    await save(updated);
  }, [foreshadows, save]);

  const resolve = useCallback(async (id: string, chapter: number) => {
    const updated = foreshadows.map(f =>
      f.id === id
        ? { ...f, status: 'resolved' as ForeshadowStatus, resolvedChapter: chapter, updatedAt: new Date().toISOString() }
        : f
    );
    setForeshadows(updated);
    await save(updated);
  }, [foreshadows, save]);

  const abandon = useCallback(async (id: string) => {
    const updated = foreshadows.map(f =>
      f.id === id
        ? { ...f, status: 'abandoned' as ForeshadowStatus, updatedAt: new Date().toISOString() }
        : f
    );
    setForeshadows(updated);
    await save(updated);
  }, [foreshadows, save]);

  const update = useCallback(async (id: string, updates: Partial<Foreshadow>) => {
    const updated = foreshadows.map(f =>
      f.id === id
        ? { ...f, ...updates, updatedAt: new Date().toISOString() }
        : f
    );
    setForeshadows(updated);
    await save(updated);
  }, [foreshadows, save]);

  const remove = useCallback(async (id: string) => {
    const updated = foreshadows.filter(f => f.id !== id);
    setForeshadows(updated);
    await save(updated);
  }, [foreshadows, save]);

  return { foreshadows, add, resolve, abandon, update, remove, isLoading, error };
}
