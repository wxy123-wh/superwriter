interface StatusBarProps {
  line?: number;
  column?: number;
  language?: string;
  encoding?: string;
}

export function StatusBar({ line = 1, column = 1, language = 'Markdown', encoding = 'UTF-8' }: StatusBarProps) {
  return (
    <footer className="status-bar">
      <div className="status-bar-left">
        <span className="status-bar-item" title="Git: 已同步">
          <span className="codicon codicon-sync"></span>
        </span>
        <span className="status-bar-item">
          <span className="codicon codicon-output"></span>
        </span>
      </div>
      <div className="status-bar-right">
        <span className="status-bar-item" title={`行 ${line}, 列 ${column}`}>
          Ln {line}, Col {column}
        </span>
        <span className="status-bar-item">{language}</span>
        <span className="status-bar-item">{encoding}</span>
        <span className="status-bar-item">Spaces: 2</span>
      </div>
    </footer>
  );
}
