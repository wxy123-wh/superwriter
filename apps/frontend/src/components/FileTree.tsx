import type { FileTreeNode as FileTreeNodeType } from '../lib/api/client';
import { FileTreeNode } from './FileTreeNode';

interface FileTreeProps {
  nodes: FileTreeNodeType[];
  onFileSelect: (path: string) => void;
  onDirectoryExpand: (path: string) => void;
  selectedPath: string | null;
  expandedPaths: Record<string, boolean>;
}

export function FileTree({ nodes, onFileSelect, onDirectoryExpand, selectedPath, expandedPaths }: FileTreeProps) {
  return (
    <nav className="filetree-nav" aria-label="文件浏览器">
      <ul className="filetree-root">
        {nodes.map((node) => (
          <FileTreeNode
            key={node.path}
            node={node}
            depth={0}
            onFileSelect={onFileSelect}
            onDirectoryExpand={onDirectoryExpand}
            selectedPath={selectedPath}
            isExpanded={!!expandedPaths[node.path]}
          />
        ))}
      </ul>
    </nav>
  );
}
