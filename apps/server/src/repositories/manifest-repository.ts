import fs from 'node:fs/promises';
import path from 'node:path';
import { v4 as uuidv4 } from 'uuid';
import {
  NovelManifest,
  Character,
  Location,
  TimelineEvent,
  TrackedObject,
  CharacterRelationship,
} from '@frontend/types/novel-manifest';

export type { NovelManifest, Character, Location, TimelineEvent, TrackedObject, CharacterRelationship };

const MANIFEST_FILENAME = 'manifest.json';
const SUPERWRITER_DIR = '.superwriter';

function getManifestPath(projectDir: string): string {
  return path.join(projectDir, SUPERWRITER_DIR, MANIFEST_FILENAME);
}

function getSuperwriterDir(projectDir: string): string {
  return path.join(projectDir, SUPERWRITER_DIR);
}

export async function ensureManifestDir(projectDir: string): Promise<void> {
  const dir = getSuperwriterDir(projectDir);
  await fs.mkdir(dir, { recursive: true });
}

export async function loadManifest(projectDir: string): Promise<NovelManifest> {
  const manifestPath = getManifestPath(projectDir);
  try {
    const content = await fs.readFile(manifestPath, 'utf-8');
    return JSON.parse(content) as NovelManifest;
  } catch (error: any) {
    if (error.code === 'ENOENT') {
      return createEmptyManifest();
    }
    throw error;
  }
}

export async function saveManifest(projectDir: string, manifest: NovelManifest): Promise<void> {
  await ensureManifestDir(projectDir);
  const manifestPath = getManifestPath(projectDir);
  await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2), 'utf-8');
}

function createEmptyManifest(): NovelManifest {
  return {
    version: '1.0.0',
    characters: [],
    locations: [],
    timeline: [],
    trackedObjects: [],
  };
}

