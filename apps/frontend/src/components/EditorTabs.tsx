interface Tab {
  path: string;
  name: string;
  isActive?: boolean;
}

interface EditorTabsProps {
  tabs: Tab[];
  activeTab?: string;
  onTabClose?: (path: string) => void;
  onTabSelect?: (path: string) => void;
}

export function EditorTabs({ tabs, activeTab, onTabClose, onTabSelect }: EditorTabsProps) {
  if (tabs.length === 0) {
    return <div className="editor-tabs editor-tabs-empty"></div>;
  }

  return (
    <div className="editor-tabs">
      {tabs.map((tab) => (
        <div
          key={tab.path}
          className={`editor-tab ${tab.path === activeTab ? 'active' : ''}`}
          onClick={() => onTabSelect?.(tab.path)}
        >
          <span className={`editor-tab-icon codicon codicon-file-code`}></span>
          <span className="editor-tab-name">{tab.name}</span>
          <button
            className="editor-tab-close"
            onClick={(e) => {
              e.stopPropagation();
              onTabClose?.(tab.path);
            }}
          >
            <span className="codicon codicon-close"></span>
          </button>
        </div>
      ))}
    </div>
  );
}
