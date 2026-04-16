export interface CharacterRelationship {
  targetId: string;
  type: 'family' | 'friend' | 'enemy' | 'lover' | 'mentor' | 'rival' | 'stranger';
  strength: 'strong' | 'medium' | 'weak';
  status: 'active' | 'strained' | 'broken';
}

export interface Character {
  id: string;
  name: string;
  aliases?: string[];
  role: 'protagonist' | 'antagonist' | 'supporting' | 'minor';
  appearance?: string;
  personality?: string;
  background?: string;
  speechPatterns?: string[];
  relationships: CharacterRelationship[];
  createdAt: string;
  updatedAt: string;
}

export interface Location {
  id: string;
  name: string;
  description?: string;
  rules?: string[];
}

export interface TimelineEvent {
  id: string;
  date?: string;
  event: string;
  chapter?: number;
}

export interface TrackedObject {
  id: string;
  name: string;
  description?: string;
  lastSeen?: { chapter: number; location: string };
}

export interface NovelManifest {
  version: string;
  characters: Character[];
  locations: Location[];
  timeline: TimelineEvent[];
  trackedObjects: TrackedObject[];
}

export function createEmptyManifest(): NovelManifest {
  return {
    version: '1.0.0',
    characters: [],
    locations: [],
    timeline: [],
    trackedObjects: [],
  };
}
