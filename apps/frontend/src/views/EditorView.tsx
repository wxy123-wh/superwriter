import { useCallback, useEffect } from 'react';
import { useOutletContext } from 'react-router';

import { MonacoEditor } from '../components/MonacoEditor';
import { ChatPanel } from '../components/ChatPanel';
import { EditorTabs } from '../components/EditorTabs';

// Context type matching AppShell Outlet context
interface EditorContext {
  localRootPath: string | null;
  selectedPath: string | null;
  fileContent: string | null;
  fileLanguage: string;
  isDirty: boolean;
  setIsDirty: (v: boolean) => void;
  saveLocalFile: () => Promise<void>;
  handleFileSelect: (path: string) => void;
  handleCreateFile: (dirPath: string) => void;
  refreshTree: () => Promise<void>;
  isLoading: boolean;
  projectId: string | null;
  cursorLine: number;
  cursorCol: number;
  setCursorPos: (line: number, col: number) => void;
}

// Default context when AppShell doesn't provide one (backward compatibility)
const defaultContext: EditorContext = {
  localRootPath: null,
  selectedPath: null,
  fileContent: null,
  fileLanguage: 'markdown',
  isDirty: false,
  setIsDirty: () => {},
  saveLocalFile: async () => {},
  handleFileSelect: () => {},
  handleCreateFile: () => {},
  refreshTree: async () => {},
  isLoading: false,
  projectId: null,
  cursorLine: 1,
  cursorCol: 1,
  setCursorPos: () => {},
};

export function EditorView() {
  const ctx = useOutletContext<EditorContext>() ?? defaultContext;
  const {
    localRootPath: _localRootPath,
    selectedPath,
    fileContent,
    fileLanguage,
    isDirty,
    setIsDirty,
    saveLocalFile,
    isLoading,
    setCursorPos,
  } = ctx;

  const handleContentChange = useCallback((newContent: string) => {
    setIsDirty(newContent !== fileContent);
  }, [setIsDirty, fileContent]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        if (isDirty) saveLocalFile();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isDirty, saveLocalFile]);

  const tabs = selectedPath ? [{ path: selectedPath, name: selectedPath.split(/[/\\]/).pop() || selectedPath, isActive: true }] : [];
  const selectedFileName = selectedPath ? selectedPath.split(/[/\\]/).pop() : null;

  return (
    <div className="app-editor-area">
      <div className="editor-container">
        <EditorTabs tabs={tabs} activeTab={selectedPath ?? undefined} />
        <div className="editor-toolbar">
          {selectedFileName && (
            <span style={{ fontSize: 12, color: 'var(--vscode-activityBar-inactiveForeground)', alignSelf: 'center', marginRight: 'auto' }}>
              {selectedFileName}
            </span>
          )}
          {isDirty && (
            <span className="dirty-indicator">● 未保存</span>
          )}
          <button
            className="btn btn-primary"
            style={{ padding: '3px 10px', fontSize: '12px' }}
            onClick={() => saveLocalFile()}
            disabled={!isDirty}
          >
            <span className="codicon codicon-save" style={{ marginRight: 4 }}></span>
            保存
          </button>
        </div>
        <div className="editor-content">
          {isLoading ? (
            <div className="editor-empty">
              <p>加载中…</p>
            </div>
          ) : selectedPath ? (
            <MonacoEditor
              value={fileContent ?? ''}
              onChange={handleContentChange}
              language={fileLanguage}
              onCursorChange={setCursorPos}
            />
          ) : (
            <div className="editor-empty">
              从左侧资源管理器选择文件开始编辑
            </div>
          )}
        </div>
      </div>
      <div className="panel">
        <div className="panel-header">
          <h3>AI 对话</h3>
        </div>
        <ChatPanel projectId={null} novelId={null} />
      </div>
    </div>
  );
}
