import { useState, useCallback } from 'react';
import { useLocation, useNavigation, useSearchParams } from 'react-router';
import { NavLink, Outlet, isRouteErrorResponse, useRouteError } from 'react-router';
import { NovelManifestProvider } from '../contexts/NovelManifestContext';
import { useQuery } from '@tanstack/react-query';

import { ApiContractError, ApiResponseError } from '../lib/api/client';
import { electronClient } from '../lib/api/electron-client';
import type { FileTreeNode } from '../lib/api/client';
import { TitleBar } from '../components/TitleBar';
import { ActivityBar } from '../components/ActivityBar';
import { StatusBar } from '../components/StatusBar';
import { ChatPanel } from '../components/ChatPanel';
import { FileTree } from '../components/FileTree';
import { SettingsPanel, type Provider } from '../components/SettingsPanel';

export type SidebarView = 'explorer' | 'navigate' | 'search' | 'chat' | 'settings';

export interface RouteSearchContext {
  projectId: string | null;
  novelId: string | null;
}

interface NavRoute {
  path: string;
  label: string;
}

const navRoutes: NavRoute[] = [
  { path: '/', label: '主页' },
  { path: '/foreshadows', label: '伏笔追踪' },
  { path: '/manifest', label: '小说大纲' },
  { path: '/skills', label: '技能工坊' },
  { path: '/consistency', label: '一致性检查' },
];

export function readRouteSearch(search: string): RouteSearchContext {
  const params = new URLSearchParams(search);
  return {
    projectId: params.get('project_id'),
    novelId: params.get('novel_id'),
  };
}

function updateTreeNode(nodes: FileTreeNode[], targetPath: string, updatedChildren: FileTreeNode[]): FileTreeNode[] {
  return nodes.map(node => {
    if (node.path === targetPath) {
      return { ...node, children: updatedChildren };
    }
    if (node.children) {
      return { ...node, children: updateTreeNode(node.children, targetPath, updatedChildren) };
    }
    return node;
  });
}

export function AppShell() {
  const location = useLocation();
  const navigation = useNavigation();
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get('project_id');
  const context = readRouteSearch(location.search);

  const [activeView, setActiveView] = useState<SidebarView>('explorer');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [cursorLine, _setCursorLine] = useState(1);
  const [cursorCol, _setCursorCol] = useState(1);
  const [fileTree, setFileTree] = useState<FileTreeNode[]>([]);
  const [expandedPaths, setExpandedPaths] = useState<Record<string, boolean>>({});
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileLanguage, setFileLanguage] = useState('markdown');
  const [isDirty, setIsDirty] = useState(false);
  const [localRootPath, setLocalRootPath] = useState<string | null>(null);

  // Provider editing state (main editor area)
  const [showProviderForm, setShowProviderForm] = useState(false);
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
  const [providerFormData, setProviderFormData] = useState({
    provider_name: '',
    base_url: '',
    api_key: '',
    model_name: '',
    temperature: '0.7',
    max_tokens: '4096',
  });
  const [providerSaving, setProviderSaving] = useState(false);

  const { refetch: refetchSettings } = useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const result = await electronClient.getSettings();
      return result.settings;
    },
    enabled: false,
  });

  const handleAddProvider = useCallback(() => {
    setEditingProvider(null);
    setProviderFormData({ provider_name: '', base_url: '', api_key: '', model_name: '', temperature: '0.7', max_tokens: '4096' });
    setShowProviderForm(true);
  }, []);

  const handleEditProvider = useCallback((provider: Provider) => {
    setEditingProvider(provider);
    setProviderFormData({
      provider_name: provider.provider_name,
      base_url: provider.base_url,
      api_key: provider.api_key,
      model_name: provider.model_name,
      temperature: String(provider.temperature),
      max_tokens: String(provider.max_tokens),
    });
    setShowProviderForm(true);
  }, []);

  const handleSaveProvider = useCallback(async () => {
    if (!providerFormData.provider_name || !providerFormData.base_url || !providerFormData.api_key || !providerFormData.model_name) return;
    setProviderSaving(true);
    try {
      await electronClient.saveProvider({
        provider_id: editingProvider?.provider_id,
        provider_name: providerFormData.provider_name,
        base_url: providerFormData.base_url,
        api_key: providerFormData.api_key,
        model_name: providerFormData.model_name,
        temperature: parseFloat(providerFormData.temperature) || 0.7,
        max_tokens: parseInt(providerFormData.max_tokens) || 4096,
      });
      await refetchSettings();
      setShowProviderForm(false);
    } finally {
      setProviderSaving(false);
    }
  }, [editingProvider, providerFormData, refetchSettings]);

  const handleCancelProvider = useCallback(() => {
    setShowProviderForm(false);
    setEditingProvider(null);
  }, []);

  const handleOpenFolder = useCallback(async () => {
    const result = await electronClient.openDirectory();
    if (result.success && result.rootPath) {
      setLocalRootPath(result.rootPath);
      const { tree } = await electronClient.readLocalDirectory({ rootPath: result.rootPath, dirPath: '' });
      setFileTree(tree);
      setExpandedPaths({});
      setSelectedPath(null);
      setFileContent(null);
    }
  }, []);

  const handleFileSelect = useCallback(async (path: string) => {
    setSelectedPath(path);
    const content = await electronClient.readLocalFile({ rootPath: localRootPath!, filePath: path });
    setFileContent(content);
    setIsDirty(false);
    const ext = path.split('.').pop()?.toLowerCase();
    setFileLanguage(ext === 'md' || ext === 'markdown' ? 'markdown' : ext === 'json' ? 'json' : 'plaintext');
  }, [localRootPath]);

  const handleDirectoryExpand = useCallback(async (path: string) => {
    const isExpanded = expandedPaths[path];
    setExpandedPaths(prev => ({ ...prev, [path]: !isExpanded }));
    if (!isExpanded && localRootPath) {
      const { tree } = await electronClient.readLocalDirectory({ rootPath: localRootPath, dirPath: path });
      setFileTree(prev => updateTreeNode(prev, path, tree));
    }
  }, [expandedPaths, localRootPath]);

  const handleCreateFile = useCallback(async (_dirPath: string) => {
    // TODO: implement file creation dialog
  }, []);

  const saveLocalFile = useCallback(async () => {
    if (!selectedPath || !localRootPath) return;
    await electronClient.saveLocalFile({ rootPath: localRootPath, filePath: selectedPath, content: fileContent! });
    setIsDirty(false);
  }, [selectedPath, localRootPath, fileContent]);

  const refreshTree = useCallback(async () => {
    if (!localRootPath) return;
    const { tree } = await electronClient.readLocalDirectory({ rootPath: localRootPath, dirPath: '' });
    setFileTree(tree);
  }, [localRootPath]);

  const handleViewChange = (view: SidebarView) => {
    if (view === activeView && sidebarOpen) {
      setSidebarOpen(false);
    } else {
      setActiveView(view);
      setSidebarOpen(true);
    }
  };

  const sidebarTitle: Record<SidebarView, string> = {
    explorer: '资源管理器',
    navigate: '功能导航',
    search: '搜索',
    chat: 'AI 对话',
    settings: '设置',
  };

  const outletContext = {
    projectId,
    novelId: context.novelId,
    localRootPath,
    selectedPath,
    fileContent,
    fileLanguage,
    isDirty,
    setIsDirty,
    saveLocalFile,
    handleFileSelect,
    handleCreateFile,
    refreshTree,
    isLoading: false,
    cursorLine,
    cursorCol,
    setCursorPos: (_line: number, _col: number) => {},
    // Provider form state
    showProviderForm,
    editingProvider,
    providerFormData,
    setProviderFormData,
    handleSaveProvider,
    handleCancelProvider,
  };

  return (
    <div className="app-shell">
      <TitleBar title={navigation.state !== 'idle' ? 'SuperWriter · 加载中…' : 'SuperWriter'} />

      <div className="app-workbench">
        <ActivityBar
          activeView={activeView}
          onViewChange={handleViewChange}
        />

        {sidebarOpen && (
          <aside className="sidebar">
            <div className="sidebar-header">
              <h3>{sidebarTitle[activeView]}</h3>
            </div>
            <div className="sidebar-content">
              {activeView === 'explorer' && (
                !localRootPath ? (
                  <div className="explorer-empty">
                    <p>打开文件夹以开始编辑</p>
                    <button type="button" className="btn btn-primary" onClick={handleOpenFolder}>
                      <span className="codicon codicon-folder-opened" style={{ marginRight: 4 }} />
                      打开文件夹
                    </button>
                  </div>
                ) : (
                  <FileTree
                    nodes={fileTree}
                    onFileSelect={handleFileSelect}
                    onDirectoryExpand={handleDirectoryExpand}
                    onCreateFile={handleCreateFile}
                    selectedPath={selectedPath}
                    expandedPaths={expandedPaths}
                  />
                )
              )}
              {activeView === 'navigate' && (
                <nav className="sidebar-nav">
                  {navRoutes.map((route) => (
                    <NavLink
                      key={route.path}
                      to={route.path}
                      end={route.path === '/'}
                      className={({ isActive }) =>
                        `sidebar-nav-link${isActive ? ' sidebar-nav-link-active' : ''}`
                      }
                    >
                      {route.label}
                    </NavLink>
                  ))}
                </nav>
              )}
              {activeView === 'search' && (
                <div className="explorer-empty">
                  <p>搜索功能开发中…</p>
                </div>
              )}
              {activeView === 'chat' && (
                <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
                  <ChatPanel projectId={context.projectId} novelId={context.novelId} />
                </div>
              )}
              {activeView === 'settings' && (
                <SettingsPanel onEditProvider={handleEditProvider} onAddProvider={handleAddProvider} />
              )}
            </div>
          </aside>
        )}

        <div className="app-main">
          <NovelManifestProvider projectId={projectId}>
            {showProviderForm ? (
              <div className="app-editor-area">
                <div className="editor-container">
                  <div className="editor-toolbar">
                    <span style={{ fontSize: 12, color: 'var(--vscode-activityBar-inactiveForeground)', alignSelf: 'center', marginRight: 'auto' }}>
                      {editingProvider ? '编辑 Provider' : '新建 Provider'}
                    </span>
                  </div>
                  <div className="editor-content" style={{ padding: 16 }}>
                    <form onSubmit={e => { e.preventDefault(); handleSaveProvider(); }}>
                      <div className="form-row">
                        <label htmlFor="provider_name">名称</label>
                        <input
                          id="provider_name"
                          type="text"
                          className="form-input"
                          value={providerFormData.provider_name}
                          onChange={e => setProviderFormData(p => ({ ...p, provider_name: e.target.value }))}
                          placeholder="例如: OpenAI"
                          required
                        />
                      </div>
                      <div className="form-row">
                        <label htmlFor="base_url">API Base URL</label>
                        <input
                          id="base_url"
                          type="url"
                          className="form-input"
                          value={providerFormData.base_url}
                          onChange={e => setProviderFormData(p => ({ ...p, base_url: e.target.value }))}
                          placeholder="https://api.openai.com/v1"
                          required
                        />
                      </div>
                      <div className="form-row">
                        <label htmlFor="api_key">API Key</label>
                        <input
                          id="api_key"
                          type="password"
                          className="form-input"
                          value={providerFormData.api_key}
                          onChange={e => setProviderFormData(p => ({ ...p, api_key: e.target.value }))}
                          placeholder="sk-..."
                          required
                        />
                      </div>
                      <div className="form-row">
                        <label htmlFor="model_name">模型</label>
                        <input
                          id="model_name"
                          type="text"
                          className="form-input"
                          value={providerFormData.model_name}
                          onChange={e => setProviderFormData(p => ({ ...p, model_name: e.target.value }))}
                          placeholder="gpt-4o"
                          required
                        />
                      </div>
                      <div className="form-row-group">
                        <div className="form-row">
                          <label htmlFor="temperature">Temperature</label>
                          <input
                            id="temperature"
                            type="number"
                            className="form-input"
                            value={providerFormData.temperature}
                            onChange={e => setProviderFormData(p => ({ ...p, temperature: e.target.value }))}
                            min="0"
                            max="2"
                            step="0.1"
                          />
                        </div>
                        <div className="form-row">
                          <label htmlFor="max_tokens">Max Tokens</label>
                          <input
                            id="max_tokens"
                            type="number"
                            className="form-input"
                            value={providerFormData.max_tokens}
                            onChange={e => setProviderFormData(p => ({ ...p, max_tokens: e.target.value }))}
                            min="1"
                          />
                        </div>
                      </div>
                      <div className="proposal-actions">
                        <button type="submit" className="btn btn-primary" disabled={providerSaving}>
                          {providerSaving ? '保存中…' : '保存'}
                        </button>
                        <button type="button" className="btn" onClick={handleCancelProvider}>
                          取消
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
                <div className="panel">
                  <div className="panel-header">
                    <h3>AI 对话</h3>
                  </div>
                  <ChatPanel projectId={context.projectId} novelId={context.novelId} />
                </div>
              </div>
            ) : (
              <Outlet context={outletContext} />
            )}
          </NovelManifestProvider>
        </div>
      </div>

      <StatusBar line={cursorLine} column={cursorCol} />
    </div>
  );
}

export function RouteErrorBoundary() {
  const error = useRouteError();
  if (isRouteErrorResponse(error)) {
    return (
      <section className="surface-panel surface-panel-error">
        <p className="eyebrow">Route error</p>
        <h2>路由加载失败</h2>
        <p>{error.status} {error.statusText}</p>
        <p>{typeof error.data === 'string' ? error.data : '无法完成当前路由。'}</p>
      </section>
    );
  }
  if (error instanceof ApiResponseError) {
    return (
      <section className="surface-panel surface-panel-error">
        <p className="eyebrow">API error</p>
        <h2>接口返回了明确错误</h2>
        <p>{error.status} · {error.code}</p>
        <p>{error.message}</p>
      </section>
    );
  }
  if (error instanceof ApiContractError) {
    return (
      <section className="surface-panel surface-panel-error">
        <p className="eyebrow">Contract drift</p>
        <h2>接口契约与前端预期不一致</h2>
        <p>{error.endpoint}</p>
        <p>{error.message}</p>
      </section>
    );
  }
  return (
    <section className="surface-panel surface-panel-error">
      <p className="eyebrow">Unexpected error</p>
      <h2>出现未处理错误</h2>
      <p>{error instanceof Error ? error.message : '未知错误'}</p>
    </section>
  );
}
