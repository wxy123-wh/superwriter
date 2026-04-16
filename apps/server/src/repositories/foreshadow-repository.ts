import fs from 'node:fs/promises';
import path from 'node:path';
import { v4 as uuidv4 } from 'uuid';
import { Foreshadow } from '@frontend/types/foreshadow';

export type { Foreshadow };

type ForeshadowInput = Omit<Foreshadow, 'id' | 'createdAt' | 'updatedAt'>;

export class ForeshadowRepository {
  private foreshadows: Foreshadow[] = [];

  private getFilePath(projectDir: string): string {
    return path.join(projectDir, '.superwriter', 'foreshadows.json');
  }

  async load(projectDir: string): Promise<Foreshadow[]> {
    const filePath = this.getFilePath(projectDir);
    try {
      const content = await fs.readFile(filePath, 'utf-8');
      this.foreshadows = JSON.parse(content) as Foreshadow[];
      return this.foreshadows;
    } catch (error: any) {
      if (error.code === 'ENOENT') {
        this.foreshadows = [];
        return [];
      }
      throw error;
    }
  }

  async save(projectDir: string): Promise<void> {
    const filePath = this.getFilePath(projectDir);
    const dirPath = path.dirname(filePath);
    await fs.mkdir(dirPath, { recursive: true });
    await fs.writeFile(filePath, JSON.stringify(this.foreshadows, null, 2), 'utf-8');
  }

  add(input: ForeshadowInput): Foreshadow {
    const now = new Date().toISOString();
    const foreshadow: Foreshadow = {
      ...input,
      id: `fs_${uuidv4().slice(0, 8)}`,
      createdAt: now,
      updatedAt: now,
    };
    this.foreshadows.push(foreshadow);
    return foreshadow;
  }

  update(id: string, updates: Partial<Foreshadow>): Foreshadow | null {
    const index = this.foreshadows.findIndex(f => f.id === id);
    if (index === -1) return null;

    this.foreshadows[index] = {
      ...this.foreshadows[index],
      ...updates,
      id,
      updatedAt: new Date().toISOString(),
    };
    return this.foreshadows[index];
  }

  resolve(id: string, chapter: number): Foreshadow | null {
    return this.update(id, { status: 'resolved', resolvedChapter: chapter });
  }

  delete(id: string): boolean {
    const index = this.foreshadows.findIndex(f => f.id === id);
    if (index === -1) return false;
    this.foreshadows.splice(index, 1);
    return true;
  }

  getByChapter(chapter: number): Foreshadow[] {
    return this.foreshadows.filter(f => f.plantedChapter === chapter);
  }

  getPending(): Foreshadow[] {
    return this.foreshadows.filter(f => f.status === 'pending');
  }
}
