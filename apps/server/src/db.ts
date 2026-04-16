import Database from 'better-sqlite3';
import path from 'node:path';

const DB_PATH = path.join(__dirname, '../../../superwriter.db');

let db: Database.Database;

export function getDb(): Database.Database {
  if (!db) {
    db = new Database(DB_PATH);
    db.pragma('journal_mode = WAL');
    initializeSchema();
  }
  return db;
}

function initializeSchema() {
  const database = db;

  // Projects table
  database.exec(`
    CREATE TABLE IF NOT EXISTS projects (
      project_id TEXT PRIMARY KEY,
      project_title TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      created_by TEXT NOT NULL,
      updated_by TEXT NOT NULL
    )
  `);

  // Novels table
  database.exec(`
    CREATE TABLE IF NOT EXISTS novels (
      novel_id TEXT PRIMARY KEY,
      project_id TEXT NOT NULL,
      novel_title TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      created_by TEXT NOT NULL,
      updated_by TEXT NOT NULL,
      FOREIGN KEY (project_id) REFERENCES projects(project_id)
    )
  `);

  // Skill objects table
  database.exec(`
    CREATE TABLE IF NOT EXISTS skill_objects (
      object_id TEXT PRIMARY KEY,
      project_id TEXT NOT NULL,
      novel_id TEXT NOT NULL,
      name TEXT NOT NULL,
      description TEXT NOT NULL,
      source_kind TEXT NOT NULL,
      donor_kind TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      created_by TEXT NOT NULL,
      updated_by TEXT NOT NULL,
      FOREIGN KEY (project_id) REFERENCES projects(project_id),
      FOREIGN KEY (novel_id) REFERENCES novels(novel_id)
    )
  `);

  // Skill revisions table
  database.exec(`
    CREATE TABLE IF NOT EXISTS skill_revisions (
      revision_id TEXT PRIMARY KEY,
      object_id TEXT NOT NULL,
      revision_number INTEGER NOT NULL,
      parent_revision_id TEXT,
      name TEXT NOT NULL,
      instruction TEXT NOT NULL,
      style_scope TEXT NOT NULL,
      is_active INTEGER NOT NULL DEFAULT 0,
      payload_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL,
      created_by TEXT NOT NULL,
      FOREIGN KEY (object_id) REFERENCES skill_objects(object_id),
      FOREIGN KEY (parent_revision_id) REFERENCES skill_revisions(revision_id)
    )
  `);

  // Ensure indexes exist
  database.exec(`
    CREATE INDEX IF NOT EXISTS idx_novels_project ON novels(project_id);
    CREATE INDEX IF NOT EXISTS idx_skill_objects_project_novel ON skill_objects(project_id, novel_id);
    CREATE INDEX IF NOT EXISTS idx_skill_revisions_object ON skill_revisions(object_id);
  `);

  // AI providers table (already exists, but ensure it has all fields)
  database.exec(`
    CREATE TABLE IF NOT EXISTS ai_provider_config (
      provider_id TEXT PRIMARY KEY,
      provider_name TEXT NOT NULL,
      base_url TEXT NOT NULL,
      api_key TEXT NOT NULL,
      model_name TEXT NOT NULL,
      temperature REAL NOT NULL DEFAULT 0.7,
      max_tokens INTEGER NOT NULL DEFAULT 4096,
      is_active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      created_by TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      updated_by TEXT NOT NULL
    )
  `);

  // Chat sessions table (already exists)
  database.exec(`
    CREATE TABLE IF NOT EXISTS chat_sessions (
      session_state_id TEXT PRIMARY KEY,
      project_id TEXT NOT NULL,
      novel_id TEXT NOT NULL,
      title TEXT,
      runtime_origin TEXT NOT NULL,
      created_at TEXT NOT NULL,
      created_by TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      updated_by TEXT NOT NULL,
      source_kind TEXT NOT NULL,
      source_ref TEXT,
      ingest_run_id TEXT
    )
  `);

  // Chat message links table (already exists)
  database.exec(`
    CREATE TABLE IF NOT EXISTS chat_message_links (
      message_state_id TEXT PRIMARY KEY,
      chat_session_id TEXT NOT NULL,
      linked_object_id TEXT,
      linked_revision_id TEXT,
      chat_message_id TEXT NOT NULL,
      chat_role TEXT NOT NULL,
      payload_json TEXT NOT NULL,
      created_at TEXT NOT NULL,
      created_by TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      updated_by TEXT NOT NULL,
      source_kind TEXT NOT NULL,
      source_ref TEXT,
      ingest_run_id TEXT,
      FOREIGN KEY (chat_session_id) REFERENCES chat_sessions(session_state_id)
    )
  `);
}

export function closeDb() {
  if (db) {
    db.close();
    db = undefined as any;
  }
}
