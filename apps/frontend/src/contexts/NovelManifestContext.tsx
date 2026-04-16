import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import { novelManifestApi } from '../lib/api/novel-manifest';
import type {
  NovelManifest,
  Character,
  Location,
  TimelineEvent,
  TrackedObject,
} from '../types/novel-manifest';
import { createEmptyManifest } from '../types/novel-manifest';

interface NovelManifestContextValue {
  manifest: NovelManifest;
  isLoading: boolean;
  error: string | null;
  // Character operations
  addCharacter: (character: Omit<Character, 'id' | 'createdAt' | 'updatedAt'>) => Promise<void>;
  updateCharacter: (characterId: string, updates: Partial<Character>) => Promise<void>;
  deleteCharacter: (characterId: string) => Promise<void>;
  // Location operations
  addLocation: (location: Omit<Location, 'id'>) => Promise<void>;
  updateLocation: (locationId: string, updates: Partial<Location>) => Promise<void>;
  deleteLocation: (locationId: string) => Promise<void>;
  // Timeline operations
  addTimelineEvent: (event: Omit<TimelineEvent, 'id'>) => Promise<void>;
  updateTimelineEvent: (eventId: string, updates: Partial<TimelineEvent>) => Promise<void>;
  deleteTimelineEvent: (eventId: string) => Promise<void>;
  // Tracked object operations
  trackObject: (obj: Omit<TrackedObject, 'id'>) => Promise<void>;
  updateTrackedObject: (objectId: string, updates: Partial<TrackedObject>) => Promise<void>;
  deleteTrackedObject: (objectId: string) => Promise<void>;
  // Manifest operations
  reloadManifest: (projectId: string) => Promise<void>;
  saveManifest: () => Promise<void>;
}

const NovelManifestContext = createContext<NovelManifestContextValue | null>(null);

interface NovelManifestProviderProps {
  children: ReactNode;
  projectId: string | null;
}

export function NovelManifestProvider({ children, projectId }: NovelManifestProviderProps) {
  const [manifest, setManifest] = useState<NovelManifest>(createEmptyManifest());
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reloadManifest = useCallback(async (projId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      await novelManifestApi.ensureDir(projId);
      const result = await novelManifestApi.load(projId);
      if (result.error) {
        setError(result.error);
        setManifest(createEmptyManifest());
      } else {
        setManifest(result.manifest || createEmptyManifest());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load manifest');
      setManifest(createEmptyManifest());
    } finally {
      setIsLoading(false);
    }
  }, []);

  const saveManifest = useCallback(async () => {
    if (!projectId) return;
    const result = await novelManifestApi.save(projectId, manifest);
    if (result.error) {
      setError(result.error);
    }
  }, [projectId, manifest]);

  const addCharacter = useCallback(async (character: Omit<Character, 'id' | 'createdAt' | 'updatedAt'>) => {
    const now = new Date().toISOString();
    const newCharacter: Character = {
      ...character,
      id: `char_${Date.now().toString(36)}`,
      createdAt: now,
      updatedAt: now,
    };
    setManifest(prev => ({
      ...prev,
      characters: [...prev.characters, newCharacter],
    }));
    if (projectId) await saveManifest();
  }, [projectId, saveManifest]);

  const updateCharacter = useCallback(async (characterId: string, updates: Partial<Character>) => {
    setManifest(prev => ({
      ...prev,
      characters: prev.characters.map(c =>
        c.id === characterId
          ? { ...c, ...updates, id: characterId, updatedAt: new Date().toISOString() }
          : c
      ),
    }));
    if (projectId) await saveManifest();
  }, [projectId, saveManifest]);

  const deleteCharacter = useCallback(async (characterId: string) => {
    setManifest(prev => ({
      ...prev,
      characters: prev.characters
        .filter(c => c.id !== characterId)
        .map(c => ({
          ...c,
          relationships: c.relationships.filter(r => r.targetId !== characterId),
        })),
    }));
    if (projectId) await saveManifest();
  }, [projectId, saveManifest]);

  const addLocation = useCallback(async (location: Omit<Location, 'id'>) => {
    const newLocation: Location = {
      ...location,
      id: `loc_${Date.now().toString(36)}`,
    };
    setManifest(prev => ({
      ...prev,
      locations: [...prev.locations, newLocation],
    }));
    if (projectId) await saveManifest();
  }, [projectId, saveManifest]);

  const updateLocation = useCallback(async (locationId: string, updates: Partial<Location>) => {
    setManifest(prev => ({
      ...prev,
      locations: prev.locations.map(l =>
        l.id === locationId ? { ...l, ...updates, id: locationId } : l
      ),
    }));
    if (projectId) await saveManifest();
  }, [projectId, saveManifest]);

  const deleteLocation = useCallback(async (locationId: string) => {
    setManifest(prev => ({
      ...prev,
      locations: prev.locations.filter(l => l.id !== locationId),
    }));
    if (projectId) await saveManifest();
  }, [projectId, saveManifest]);

  const addTimelineEvent = useCallback(async (event: Omit<TimelineEvent, 'id'>) => {
    const newEvent: TimelineEvent = {
      ...event,
      id: `evt_${Date.now().toString(36)}`,
    };
    setManifest(prev => ({
      ...prev,
      timeline: [...prev.timeline, newEvent],
    }));
    if (projectId) await saveManifest();
  }, [projectId, saveManifest]);

  const updateTimelineEvent = useCallback(async (eventId: string, updates: Partial<TimelineEvent>) => {
    setManifest(prev => ({
      ...prev,
      timeline: prev.timeline.map(e =>
        e.id === eventId ? { ...e, ...updates, id: eventId } : e
      ),
    }));
    if (projectId) await saveManifest();
  }, [projectId, saveManifest]);

  const deleteTimelineEvent = useCallback(async (eventId: string) => {
    setManifest(prev => ({
      ...prev,
      timeline: prev.timeline.filter(e => e.id !== eventId),
    }));
    if (projectId) await saveManifest();
  }, [projectId, saveManifest]);

  const trackObject = useCallback(async (obj: Omit<TrackedObject, 'id'>) => {
    const newObj: TrackedObject = {
      ...obj,
      id: `obj_${Date.now().toString(36)}`,
    };
    setManifest(prev => ({
      ...prev,
      trackedObjects: [...prev.trackedObjects, newObj],
    }));
    if (projectId) await saveManifest();
  }, [projectId, saveManifest]);

  const updateTrackedObject = useCallback(async (objectId: string, updates: Partial<TrackedObject>) => {
    setManifest(prev => ({
      ...prev,
      trackedObjects: prev.trackedObjects.map(o =>
        o.id === objectId ? { ...o, ...updates, id: objectId } : o
      ),
    }));
    if (projectId) await saveManifest();
  }, [projectId, saveManifest]);

  const deleteTrackedObject = useCallback(async (objectId: string) => {
    setManifest(prev => ({
      ...prev,
      trackedObjects: prev.trackedObjects.filter(o => o.id !== objectId),
    }));
    if (projectId) await saveManifest();
  }, [projectId, saveManifest]);

  const value: NovelManifestContextValue = {
    manifest,
    isLoading,
    error,
    addCharacter,
    updateCharacter,
    deleteCharacter,
    addLocation,
    updateLocation,
    deleteLocation,
    addTimelineEvent,
    updateTimelineEvent,
    deleteTimelineEvent,
    trackObject,
    updateTrackedObject,
    deleteTrackedObject,
    reloadManifest,
    saveManifest,
  };

  return (
    <NovelManifestContext.Provider value={value}>
      {children}
    </NovelManifestContext.Provider>
  );
}

export function useNovelManifest(): NovelManifestContextValue {
  const context = useContext(NovelManifestContext);
  if (!context) {
    throw new Error('useNovelManifest must be used within a NovelManifestProvider');
  }
  return context;
}
