/**
 * Snapshot Repository
 * Handles persistence of chapter snapshots to file system
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { ChapterSnapshot, CharacterState, WorldState } from '@frontend/types/chapter-snapshot';

export type { ChapterSnapshot, CharacterState, WorldState };

function getSnapshotsDir(projectDir: string): string {
  return path.join(projectDir, '.superwriter', 'state-snapshots');
}

function getSnapshotFilePath(projectDir: string, chapter: number): string {
  return path.join(getSnapshotsDir(projectDir), `chapter-${chapter.toString().padStart(3, '0')}.json`);
}

export class SnapshotRepository {
  /**
   * Load a specific chapter snapshot
   */
  async load(projectDir: string, chapter: number): Promise<ChapterSnapshot | null> {
    const filePath = getSnapshotFilePath(projectDir, chapter);
    try {
      const content = await fs.readFile(filePath, 'utf-8');
      return JSON.parse(content) as ChapterSnapshot;
    } catch (error: any) {
      if (error.code === 'ENOENT') {
        return null;
      }
      throw error;
    }
  }

  /**
   * Save a chapter snapshot
   */
  async save(projectDir: string, snapshot: ChapterSnapshot): Promise<void> {
    const snapshotsDir = getSnapshotsDir(projectDir);

    // Ensure directory exists
    await fs.mkdir(snapshotsDir, { recursive: true });

    const filePath = getSnapshotFilePath(projectDir, snapshot.chapterNumber);
    await fs.writeFile(filePath, JSON.stringify(snapshot, null, 2), 'utf-8');
  }

  /**
   * Get the latest snapshot (highest chapter number)
   */
  async getLatest(projectDir: string): Promise<ChapterSnapshot | null> {
    const snapshotsDir = getSnapshotsDir(projectDir);
    try {
      const entries = await fs.readdir(snapshotsDir);
      const snapshotFiles = entries.filter(f => f.startsWith('chapter-') && f.endsWith('.json'));

      if (snapshotFiles.length === 0) {
        return null;
      }

      // Parse chapter numbers and find the highest
      let latestSnapshot: ChapterSnapshot | null = null;
      let latestChapter = -1;

      for (const file of snapshotFiles) {
        const chapterNum = parseInt(file.replace('chapter-', '').replace('.json', ''), 10);
        if (!isNaN(chapterNum) && chapterNum > latestChapter) {
          const content = await fs.readFile(path.join(snapshotsDir, file), 'utf-8');
          const snapshot = JSON.parse(content) as ChapterSnapshot;
          latestSnapshot = snapshot;
          latestChapter = chapterNum;
        }
      }

      return latestSnapshot;
    } catch (error: any) {
      if (error.code === 'ENOENT') {
        return null;
      }
      throw error;
    }
  }

  /**
   * Get all snapshots sorted by chapter number
   */
  async getAll(projectDir: string): Promise<ChapterSnapshot[]> {
    const snapshotsDir = getSnapshotsDir(projectDir);
    try {
      const entries = await fs.readdir(snapshotsDir);
      const snapshotFiles = entries.filter(f => f.startsWith('chapter-') && f.endsWith('.json'));

      const snapshots: ChapterSnapshot[] = [];

      for (const file of snapshotFiles) {
        const content = await fs.readFile(path.join(snapshotsDir, file), 'utf-8');
        snapshots.push(JSON.parse(content) as ChapterSnapshot);
      }

      // Sort by chapter number
      snapshots.sort((a, b) => a.chapterNumber - b.chapterNumber);

      return snapshots;
    } catch (error: any) {
      if (error.code === 'ENOENT') {
        return [];
      }
      throw error;
    }
  }

  /**
   * Delete a specific chapter snapshot
   */
  async delete(projectDir: string, chapter: number): Promise<void> {
    const filePath = getSnapshotFilePath(projectDir, chapter);
    try {
      await fs.unlink(filePath);
    } catch (error: any) {
      if (error.code !== 'ENOENT') {
        throw error;
      }
    }
  }
}
