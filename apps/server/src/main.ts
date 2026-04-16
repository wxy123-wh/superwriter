import { app, BrowserWindow, ipcMain } from 'electron';
import path from 'node:path';
import fs from 'node:fs/promises';
import { v4 as uuidv4 } from 'uuid';
import { getDb, closeDb } from './db.js';
import { ForeshadowRepository, type Foreshadow } from './repositories/foreshadow-repository.js';
import { SnapshotRepository, type ChapterSnapshot } from './repositories/snapshot-repository.js';
import { extractContent, type ExtractedContent } from './services/content-extractor.js';
import * as manifestRepo from './repositories/manifest-repository.js';
import type { NovelManifest } from './repositories/manifest-repository.js';

function getNovelsDir(novelId: string): string {
  return path.join(app.getPath('userData'), 'novels', novelId);
}

function getProjectDir(projectId: string): string {
  return path.join(app.getPath('userData'), 'projects', projectId);
}

function safeJoin(base: string, target: string): string {
  const resolved = path.resolve(base, target);
  if (!resolved.startsWith(base)) {
    throw new Error('Invalid path traversal attempt');
  }
  return resolved;
}

let mainWindow: BrowserWindow | null = null;

function createWindow(isDev: boolean) {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: 'SuperWriter',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    mainWindow.loadURL('http://127.0.0.1:5173');
    mainWindow.webContents.openDevTools();
  } else {
    const indexPath = path.join(__dirname, '../..', 'frontend', 'dist', 'index.html');
    mainWindow.loadFile(indexPath);
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
  createWindow(isDev);
  registerIpcHandlers();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow(isDev);
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  closeDb();
});

function now(): string {
  return new Date().toISOString();
}

// IPC Handlers
function registerIpcHandlers() {
  ipcMain.handle('ping', () => 'pong');

  // Workspace root directory (set by user via open folder)
  let workspaceRoot: string | null = null;

  // Open directory dialog
  ipcMain.handle('openDirectory', async () => {
    const { dialog } = await import('electron');
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ['openDirectory'],
      title: '选择工作目录',
    });

    if (result.canceled || result.filePaths.length === 0) {
      return { success: false, rootPath: null };
    }

    workspaceRoot = result.filePaths[0];
    return { success: true, rootPath: workspaceRoot };
  });

  // Set workspace root explicitly
  ipcMain.handle('setWorkspaceRoot', (_, params: { root_path: string }) => {
    workspaceRoot = params.root_path;
    return { success: true };
  });

  // Read local directory (outside novels/)
  ipcMain.handle('readLocalDirectory', async (_, params: { root_path: string; dir_path: string }) => {
    try {
      const baseDir = params.root_path;
      const targetPath = path.join(baseDir, params.dir_path || '');

      const entries = await fs.readdir(targetPath, { withFileTypes: true });
      const tree = [];

      for (const entry of entries) {
        if (entry.name.startsWith('.')) continue;
        const entryPath = path.join(params.dir_path || '', entry.name);
        if (entry.isDirectory()) {
          tree.push({ name: entry.name, path: entryPath, kind: 'directory' });
        } else {
          tree.push({ name: entry.name, path: entryPath, kind: 'file' });
        }
      }

      tree.sort((a, b) => {
        if (a.kind !== b.kind) return a.kind === 'directory' ? -1 : 1;
        return a.name.localeCompare(b.name);
      });

      return { tree };
    } catch (error: any) {
      if (error.code === 'ENOENT') return { tree: [] };
      throw error;
    }
  });

  // Read local file
  ipcMain.handle('readLocalFile', async (_, params: { root_path: string; file_path: string }) => {
    const filePath = path.join(params.root_path, params.file_path);
    try {
      const content = await fs.readFile(filePath, 'utf-8');
      return { content };
    } catch (error: any) {
      if (error.code === 'ENOENT') return { content: '' };
      throw error;
    }
  });

  // Save local file
  ipcMain.handle('saveLocalFile', async (_, params: { root_path: string; file_path: string; content: string }) => {
    const filePath = path.join(params.root_path, params.file_path);
    try {
      await fs.writeFile(filePath, params.content, 'utf-8');
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // Create local file
  ipcMain.handle('createLocalFile', async (_, params: { root_path: string; file_path: string }) => {
    const filePath = path.join(params.root_path, params.file_path);
    try {
      await fs.writeFile(filePath, '', 'utf-8');
      return { success: true, path: filePath };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // Foreshadow IPC handlers
  const foreshadowRepo = new ForeshadowRepository();

  ipcMain.handle('loadForeshadows', async (_, params: { projectId: string }) => {
    if (!workspaceRoot) return { foreshadows: [] as Foreshadow[] };
    try {
      const foreshadows = await foreshadowRepo.load(workspaceRoot);
      return { foreshadows };
    } catch (error: any) {
      return { foreshadows: [] as Foreshadow[], error: error.message };
    }
  });

  ipcMain.handle('saveForeshadows', async (_, params: { projectId: string; foreshadows: Foreshadow[] }) => {
    if (!workspaceRoot) return { success: false, error: 'No workspace opened' };
    try {
      foreshadowRepo['foreshadows'] = params.foreshadows;
      await foreshadowRepo.save(workspaceRoot);
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // Novel Manifest IPC handlers
  ipcMain.handle('ensureManifestDir', async (_, params: { projectId: string }) => {
    if (!workspaceRoot) return { success: false, error: 'No workspace opened' };
    try {
      await manifestRepo.ensureManifestDir(workspaceRoot);
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('loadNovelManifest', async (_, params: { projectId: string }) => {
    if (!workspaceRoot) return { manifest: null, error: 'No workspace opened' };
    try {
      const manifest = await manifestRepo.loadManifest(workspaceRoot);
      return { manifest };
    } catch (error: any) {
      return { manifest: null, error: error.message };
    }
  });

  ipcMain.handle('saveNovelManifest', async (_, params: { projectId: string; manifest: manifestRepo.NovelManifest }) => {
    if (!workspaceRoot) return { success: false, error: 'No workspace opened' };
    try {
      await manifestRepo.saveManifest(workspaceRoot, params.manifest);
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // Chapter Snapshot IPC handlers
  const snapshotRepo = new SnapshotRepository();

  ipcMain.handle('loadChapterSnapshot', async (_, params: { projectId: string; chapter: number }) => {
    if (!workspaceRoot) return { snapshot: null, error: 'No workspace opened' };
    try {
      const snapshot = await snapshotRepo.load(workspaceRoot, params.chapter);
      return { snapshot };
    } catch (error: any) {
      return { snapshot: null, error: error.message };
    }
  });

  ipcMain.handle('saveChapterSnapshot', async (_, params: { projectId: string; snapshot: ChapterSnapshot }) => {
    if (!workspaceRoot) return { success: false, error: 'No workspace opened' };
    try {
      await snapshotRepo.save(workspaceRoot, params.snapshot);
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('getAllSnapshots', async (_, params: { projectId: string }) => {
    if (!workspaceRoot) return { snapshots: [], error: 'No workspace opened' };
    try {
      const snapshots = await snapshotRepo.getAll(workspaceRoot);
      return { snapshots };
    } catch (error: any) {
      return { snapshots: [], error: error.message };
    }
  });

  ipcMain.handle('extractChapterContent', async (_, params: { projectId: string; chapter: number; content: string }) => {
    try {
      const extracted = extractContent(params.content);
      return { extracted };
    } catch (error: any) {
      return { extracted: null, error: error.message };
    }
  });

  // Startup - returns all workspace contexts
  ipcMain.handle('getStartup', () => {
    const db = getDb();
    const projects = db.prepare('SELECT project_id, project_title FROM projects').all() as Array<{project_id: string; project_title: string}>;
    const workspaces = [];

    for (const project of projects) {
      const novels = db.prepare('SELECT novel_id, novel_title FROM novels WHERE project_id = ?').all(project.project_id) as Array<{novel_id: string; novel_title: string}>;
      for (const novel of novels) {
        workspaces.push({
          project_id: project.project_id,
          project_title: project.project_title,
          novel_id: novel.novel_id,
          novel_title: novel.novel_title,
        });
      }
    }

    return {
      workspace_contexts: workspaces,
      has_workspace_contexts: workspaces.length > 0,
    };
  });

  // Create workspace (project + novel)
  ipcMain.handle('createWorkspace', (_, params: { novel_title: string; project_title?: string; folder_path?: string }) => {
    const db = getDb();
    const projectId = `proj_${uuidv4().slice(0, 8)}`;
    const novelId = `nov_${uuidv4().slice(0, 8)}`;
    const ts = now();

    db.prepare('INSERT INTO projects (project_id, project_title, created_at, updated_at, created_by, updated_by) VALUES (?, ?, ?, ?, ?, ?)').run(
      projectId,
      params.project_title || params.novel_title,
      ts, ts, 'user', 'user'
    );

    db.prepare('INSERT INTO novels (novel_id, project_id, novel_title, created_at, updated_at, created_by, updated_by) VALUES (?, ?, ?, ?, ?, ?, ?)').run(
      novelId,
      projectId,
      params.novel_title,
      ts, ts, 'user', 'user'
    );

    return {
      success: true,
      projectId,
      novelId,
      manifest_path: `novels/${novelId}/manifest.json`,
    };
  });

  // Get skills for a project/novel
  ipcMain.handle('getSkills', (_, params: { project_id: string; novel_id: string }) => {
    const db = getDb();

    const skills = db.prepare(`
      SELECT o.object_id, o.name, o.description, o.source_kind, o.donor_kind,
             r.revision_id, r.revision_number, r.parent_revision_id,
             r.name as rev_name, r.instruction, r.style_scope, r.is_active, r.payload_json
      FROM skill_objects o
      JOIN skill_revisions r ON o.object_id = r.object_id
      WHERE o.project_id = ? AND o.novel_id = ?
      GROUP BY o.object_id
    `).all(params.project_id, params.novel_id) as Array<any>;

    const skillSnapshots = skills.map(s => ({
      object_id: s.object_id,
      revision_id: s.revision_id,
      revision_number: s.revision_number,
      name: s.rev_name || s.name,
      description: s.description,
      instruction: s.instruction,
      style_scope: s.style_scope,
      is_active: Boolean(s.is_active),
      source_kind: s.source_kind,
      donor_kind: s.donor_kind,
      payload: JSON.parse(s.payload_json || '{}'),
    }));

    return {
      project_id: params.project_id,
      novel_id: params.novel_id,
      skills: skillSnapshots,
      selected_skill: skillSnapshots[0] || null,
      versions: [],
      comparison: null,
    };
  });

  // Upsert skill (create or update)
  ipcMain.handle('upsertSkill', (_, params: any) => {
    const db = getDb();
    const ts = now();

    if (params.action === 'create') {
      const objectId = `skobj_${uuidv4().slice(0, 8)}`;
      const revisionId = `skrev_${uuidv4().slice(0, 8)}`;

      db.prepare(`INSERT INTO skill_objects (object_id, project_id, novel_id, name, description, source_kind, donor_kind, created_at, updated_at, created_by, updated_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(
        objectId, params.project_id || '', params.novel_id || '',
        params.name, params.description || '', 'manual', null, ts, ts, 'user', 'user'
      );

      db.prepare(`INSERT INTO skill_revisions (revision_id, object_id, revision_number, parent_revision_id, name, instruction, style_scope, is_active, payload_json, created_at, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(
        revisionId, objectId, 1, null,
        params.name, params.instruction, params.style_scope || '',
        params.is_active ? 1 : 0, '{}', ts, 'user'
      );

      return { success: true, object_id: objectId, revision_id: revisionId };
    } else if (params.action === 'update') {
      const objectId = params.skill_object_id;
      const existing = db.prepare('SELECT revision_number FROM skill_revisions WHERE object_id = ? ORDER BY revision_number DESC LIMIT 1').get(objectId) as any;
      const newRevisionNumber = (existing?.revision_number || 0) + 1;
      const revisionId = `skrev_${uuidv4().slice(0, 8)}`;

      db.prepare(`INSERT INTO skill_revisions (revision_id, object_id, revision_number, parent_revision_id, name, instruction, style_scope, is_active, payload_json, created_at, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(
        revisionId, objectId, newRevisionNumber, params.base_revision_id || null,
        params.name || '', params.instruction || '', params.style_scope || '',
        params.is_active ? 1 : 0, '{}', ts, 'user'
      );

      return { success: true, revision_id: revisionId };
    }

    return { success: false, error: 'Unknown action' };
  });

  // Rollback skill to a previous revision
  ipcMain.handle('rollbackSkill', (_, params: { skill_object_id: string; target_revision_id: string }) => {
    const db = getDb();
    const target = db.prepare('SELECT * FROM skill_revisions WHERE revision_id = ?').get(params.target_revision_id) as any;
    if (!target) return { success: false, error: 'Revision not found' };

    const latest = db.prepare('SELECT revision_number FROM skill_revisions WHERE object_id = ? ORDER BY revision_number DESC LIMIT 1').get(params.skill_object_id) as any;
    const newRevisionNumber = (latest?.revision_number || 0) + 1;
    const newRevisionId = `skrev_${uuidv4().slice(0, 8)}`;
    const ts = now();

    db.prepare(`INSERT INTO skill_revisions (revision_id, object_id, revision_number, parent_revision_id, name, instruction, style_scope, is_active, payload_json, created_at, created_by)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(
      newRevisionId, params.skill_object_id, newRevisionNumber, params.target_revision_id,
      target.name, target.instruction, target.style_scope, target.is_active, target.payload_json, ts, 'user'
    );

    return { success: true, revision_id: newRevisionId };
  });

  // Get settings (AI providers)
  ipcMain.handle('getSettings', () => {
    const db = getDb();
    const providers = db.prepare('SELECT * FROM ai_provider_config').all() as Array<any>;

    return {
      providers: providers.map(p => ({
        provider_id: p.provider_id,
        provider_name: p.provider_name,
        base_url: p.base_url,
        api_key: p.api_key,
        model_name: p.model_name,
        temperature: p.temperature,
        max_tokens: p.max_tokens,
        is_active: Boolean(p.is_active),
      })),
      active_provider: providers.find(p => p.is_active) || null,
    };
  });

  // Save provider
  ipcMain.handle('saveProvider', (_, params: any) => {
    const db = getDb();
    const ts = now();
    const providerId = params.provider_id || `prov_${uuidv4().slice(0, 8)}`;

    const existing = db.prepare('SELECT provider_id FROM ai_provider_config WHERE provider_id = ?').get(providerId);
    if (existing) {
      db.prepare(`UPDATE ai_provider_config SET provider_name = ?, base_url = ?, api_key = ?, model_name = ?, temperature = ?, max_tokens = ?, updated_at = ?
                   WHERE provider_id = ?`).run(
        params.provider_name, params.base_url, params.api_key, params.model_name,
        params.temperature || 0.7, params.max_tokens || 4096, ts, providerId
      );
    } else {
      db.prepare(`INSERT INTO ai_provider_config (provider_id, provider_name, base_url, api_key, model_name, temperature, max_tokens, is_active, created_at, created_by, updated_at, updated_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(
        providerId, params.provider_name, params.base_url, params.api_key, params.model_name,
        params.temperature || 0.7, params.max_tokens || 4096, 0, ts, 'user', ts, 'user'
      );
    }

    return { success: true, provider_id: providerId };
  });

  // Activate provider
  ipcMain.handle('activateProvider', (_, params: { provider_id: string }) => {
    const db = getDb();
    const ts = now();
    db.prepare('UPDATE ai_provider_config SET is_active = 0, updated_at = ?').run(ts);
    db.prepare('UPDATE ai_provider_config SET is_active = 1, updated_at = ? WHERE provider_id = ?').run(ts, params.provider_id);
    return { success: true };
  });

  // Delete provider
  ipcMain.handle('deleteProvider', (_, params: { provider_id: string }) => {
    const db = getDb();
    db.prepare('DELETE FROM ai_provider_config WHERE provider_id = ?').run(params.provider_id);
    return { success: true };
  });

  // Test provider (simple connectivity check)
  ipcMain.handle('testProvider', async (_, params: { provider_id: string }) => {
    const db = getDb();
    const provider = db.prepare('SELECT * FROM ai_provider_config WHERE provider_id = ?').get(params.provider_id) as any;
    if (!provider) return { success: false, error: 'Provider not found' };

    try {
      const response = await fetch(provider.base_url + '/models', {
        headers: { 'Authorization': `Bearer ${provider.api_key}` },
      });
      return { success: response.ok, status: response.status };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // Import skill
  ipcMain.handle('importSkill', (_, params: any) => {
    const db = getDb();
    const ts = now();
    const objectId = `skobj_${uuidv4().slice(0, 8)}`;
    const revisionId = `skrev_${uuidv4().slice(0, 8)}`;

    db.prepare(`INSERT INTO skill_objects (object_id, project_id, novel_id, name, description, source_kind, donor_kind, created_at, updated_at, created_by, updated_by)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(
      objectId, params.project_id || '', params.novel_id || '',
      params.name, params.description || '', 'imported', params.donor_kind || null, ts, ts, 'user', 'user'
    );

    db.prepare(`INSERT INTO skill_revisions (revision_id, object_id, revision_number, parent_revision_id, name, instruction, style_scope, is_active, payload_json, created_at, created_by)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(
      revisionId, objectId, 1, null,
      params.name, params.instruction, params.style_scope || '',
      params.is_active ? 1 : 0, '{}', ts, 'user'
    );

    return { success: true, object_id: objectId, revision_id: revisionId };
  });

  // Read directory (workspace files)
  ipcMain.handle('readDirectory', async (_, params: { project_id: string; novel_id: string; dir_path: string }) => {
    try {
      const baseDir = getNovelsDir(params.novel_id);
      const targetPath = safeJoin(baseDir, params.dir_path || '');

      const entries = await fs.readdir(targetPath, { withFileTypes: true });
      const tree = [];

      for (const entry of entries) {
        if (entry.name.startsWith('.')) continue; // skip hidden files
        const entryPath = path.join(params.dir_path || '', entry.name);
        if (entry.isDirectory()) {
          tree.push({ name: entry.name, path: entryPath, kind: 'directory' });
        } else {
          tree.push({ name: entry.name, path: entryPath, kind: 'file' });
        }
      }

      // Sort: directories first, then files, alphabetically
      tree.sort((a, b) => {
        if (a.kind !== b.kind) return a.kind === 'directory' ? -1 : 1;
        return a.name.localeCompare(b.name);
      });

      return { tree };
    } catch (error: any) {
      if (error.code === 'ENOENT') return { tree: [] };
      throw error;
    }
  });

  // Read file
  ipcMain.handle('readFile', async (_, params: { project_id: string; novel_id: string; file_path: string }) => {
    const baseDir = getNovelsDir(params.novel_id);
    const filePath = safeJoin(baseDir, params.file_path);
    try {
      const content = await fs.readFile(filePath, 'utf-8');
      return { content };
    } catch (error: any) {
      if (error.code === 'ENOENT') return { content: '' };
      throw error;
    }
  });

  // Send chat message with AI provider
  ipcMain.handle('sendChat', async (_, params: any) => {
    const db = getDb();
    const sessionId = params.session_id || `sess_${uuidv4().slice(0, 8)}`;
    const userMessageId = `msg_${uuidv4().slice(0, 8)}`;
    const assistantMessageId = `msg_${uuidv4().slice(0, 8)}`;
    const ts = now();

    // Create session if doesn't exist
    const existingSession = db.prepare('SELECT session_state_id FROM chat_sessions WHERE session_state_id = ?').get(sessionId);
    if (!existingSession) {
      db.prepare(`INSERT INTO chat_sessions (session_state_id, project_id, novel_id, title, runtime_origin, created_at, created_by, updated_at, created_by, source_kind)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(
        sessionId, params.project_id, params.novel_id,
        'Chat Session', params.workbench_type || 'chat', ts, 'user', ts, 'user', 'chat_surface'
      );
    }

    // Store user message
    db.prepare(`INSERT INTO chat_message_links (message_state_id, chat_session_id, chat_message_id, chat_role, payload_json, created_at, created_by, updated_at, updated_by, source_kind)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(
      userMessageId, sessionId, userMessageId, 'user',
      JSON.stringify({ content: params.user_message }), ts, 'user', ts, 'user', 'chat_surface'
    );

    // Get active provider
    const providers = db.prepare('SELECT * FROM ai_provider_config WHERE is_active = 1').all() as any[];
    if (!providers.length) {
      return {
        session_id: sessionId,
        user_message_state_id: userMessageId,
        assistant_message_state_id: assistantMessageId,
        assistant_content: 'No AI provider configured. Please add and activate an AI provider in settings.',
      };
    }

    const provider = providers[0];
    let assistantContent = '';

    try {
      const response = await fetch(`${provider.base_url}/chat/completions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${provider.api_key}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: provider.model_name,
          messages: [{ role: 'user', content: params.user_message }],
          temperature: provider.temperature,
          max_tokens: provider.max_tokens,
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        assistantContent = `AI API error (${response.status}): ${errorText}`;
      } else {
        const data = await response.json() as any;
        assistantContent = data.choices?.[0]?.message?.content || 'No response from AI';
      }
    } catch (error: any) {
      assistantContent = `Failed to connect to AI provider: ${error.message}`;
    }

    // Store assistant message
    db.prepare(`INSERT INTO chat_message_links (message_state_id, chat_session_id, chat_message_id, chat_role, payload_json, created_at, created_by, updated_at, updated_by, source_kind)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(
      assistantMessageId, sessionId, assistantMessageId, 'assistant',
      JSON.stringify({ content: assistantContent }), ts, 'user', ts, 'user', 'chat_surface'
    );

    return {
      session_id: sessionId,
      user_message_state_id: userMessageId,
      assistant_message_state_id: assistantMessageId,
      assistant_content: assistantContent,
    };
  });
}
