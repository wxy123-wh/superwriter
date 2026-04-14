import { useState, useCallback, useEffect } from 'react';
import { useLocation } from 'react-router';
import { readRouteSearch } from '../app/AppShell';
import { apiClient } from '../lib/api/client';
import { isElectron } from '../lib/api/electron-client';
import { MonacoEditor } from '../components/MonacoEditor';
import { FileTree } from '../components/FileTree';
import type { FileTreeNode } from '../lib/api/client';

export function EditorView() {
  const location = useLocation();
  const context = readRouteSearch(location.search);

  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileTree, setFileTree] = useState<FileTreeNode[]>([]);
  const [fileContent, setFileContent] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [expandedPaths, setExpandedPaths] = useState<Record<string, boolean>>({});

  const projectId = context.projectId ?? '';
  const novelId = context.novelId ?? '';

  const loadDirectory = useCallback(async (dirPath: string): Promise<FileTreeNode[]> => {
    if (!projectId || !novelId) return [];
    if (isElectron()) {
      const result = await apiClient.readDirectory({ projectId, novelId, dirPath });
      return result.tree;
    }
    return apiClient.readDirectory({ projectId, novelId, dirPath }).then(r => r.tree);
  }, [projectId, novelId]);

  const loadFile = useCallback(async (filePath: string) => {
    if (!projectId || !novelId) return;
    setLoading(true);
    try {
      if (isElectron()) {
        const result = await apiClient.readFile({ projectId, novelId, filePath });
        setFileContent(result.content);
      } else {
        const result = await apiClient.readFile({ projectId, novelId, filePath });
        setFileContent(result.content);
      }
    } finally {
      setLoading(false);
    }
  }, [projectId, novelId]);

  const handleFileSelect = useCallback((path: string) => {
    setSelectedPath(path);
    loadFile(path);
  }, [loadFile]);

  const handleDirectoryExpand = useCallback(async (dirPath: string) => {
    const isOpen = !!expandedPaths[dirPath];
    if (isOpen) {
      setExpandedPaths(prev => ({ ...prev, [dirPath]: false }));
    } else {
      const children = await loadDirectory(dirPath);
      setFileTree(prev => updateTreeNodes(prev, dirPath, children));
      setExpandedPaths(prev => ({ ...prev, [dirPath]: true }));
    }
  }, [expandedPaths, loadDirectory]);

  useEffect(() => {
    if (!projectId || !novelId) return;
    loadDirectory('').then(tree => setFileTree(tree));
  }, [projectId, novelId, loadDirectory]);

  const handleContentChange = useCallback((newContent: string) => {
    setFileContent(newContent);
    // TODO: implement save mutation
  }, [selectedPath]);

  return (
    <div className="editor-layout">
      <aside className="editor-filetree surface-panel">
        <div className="filetree-header">
          <h3>文件</h3>
        </div>
        <FileTree
          nodes={fileTree}
          onFileSelect={handleFileSelect}
          onDirectoryExpand={handleDirectoryExpand}
          selectedPath={selectedPath}
          expandedPaths={expandedPaths}
        />
      </aside>
      <main className="editor-monaco">
        {loading ? (
          <div className="surface-panel" style={{ padding: '2rem', textAlign: 'center' }}>
            <p>加载中…</p>
          </div>
        ) : selectedPath ? (
          <MonacoEditor
            value={fileContent}
            onChange={handleContentChange}
            language="markdown"
          />
        ) : (
          <div className="surface-panel" style={{ padding: '2rem', textAlign: 'center' }}>
            <p>从侧边选择一个文件开始编辑</p>
          </div>
        )}
      </main>
    </div>
  );
}

function updateTreeNodes(nodes: FileTreeNode[], dirPath: string, children: FileTreeNode[]): FileTreeNode[] {
  return nodes.map(node => {
    if (node.path === dirPath && node.kind === 'directory') {
      return { ...node, children };
    }
    if (node.children) {
      return { ...node, children: updateTreeNodes(node.children, dirPath, children) };
    }
    return node;
  });
}
