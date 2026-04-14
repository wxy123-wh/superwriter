import type { FileTreeNode as FileTreeNodeType } from '../lib/api/client';

interface FileTreeNodeProps {
  node: FileTreeNodeType;
  depth: number;
  onFileSelect: (path: string) => void;
  onDirectoryExpand: (path: string) => void;
  selectedPath: string | null;
  isExpanded: boolean;
}

export function FileTreeNode({ node, depth, onFileSelect, onDirectoryExpand, selectedPath, isExpanded }: FileTreeNodeProps) {
  const handleClick = () => {
    if (node.kind === 'directory') {
      onDirectoryExpand(node.path);
    } else {
      onFileSelect(node.path);
    }
  };

  const isSelected = node.kind === 'file' && selectedPath === node.path;

  return (
    <li className="tree-node-item">
      <button
        type="button"
        className={`tree-node-btn ${isSelected ? 'tree-node-btn-selected' : ''}`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={handleClick}
      >
        {node.kind === 'directory' && (
          <span className="tree-chevron">{isExpanded ? '▼' : '▶'}</span>
        )}
        <span className="tree-icon">{node.kind === 'directory' ? '📁' : '📄'}</span>
        <span className="tree-name">{node.name}</span>
      </button>
      {node.kind === 'directory' && isExpanded && node.children && (
        <ul className="tree-children">
          {node.children.map((child) => (
            <FileTreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              onFileSelect={onFileSelect}
              onDirectoryExpand={onDirectoryExpand}
              selectedPath={selectedPath}
              isExpanded={isExpanded}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
