export interface CharacterState {
  characterId: string;
  name: string;
  location: string;
  emotionalState: string;
  status: "alive" | "dead" | "unknown";
  recentEvents: string[];
}

export interface WorldState {
  currentTimeline: string;
  activeConflicts: string[];
  revealedSecrets: string[];
  pendingMysteries: number;
}

export interface ChapterSnapshot {
  chapterNumber: number;
  chapterTitle?: string;
  summary?: string;
  characterStates: CharacterState[];
  worldState: WorldState;
  timestamp: string;
}

export interface ExtractedContent {
  characters: string[];
  locations: string[];
  timeMarkers: string[];
  objectMentions: string[];
}

export interface NovelManifest {
  characters: Array<{
    characterId: string;
    name: string;
    defaultLocation?: string;
  }>;
  locations: Array<{
    locationId: string;
    name: string;
  }>;
  trackedObjects: Array<{
    objectId: string;
    name: string;
    description?: string;
  }>;
}

export type ConsistencyIssueType = "character_conflict" | "location_conflict" | "timeline_error" | "object_missing";
export type ConsistencySeverity = "error" | "warning";

export interface ConsistencyIssue {
  type: ConsistencyIssueType;
  severity: ConsistencySeverity;
  message: string;
  chapter: number;
  details: Record<string, unknown>;
}
