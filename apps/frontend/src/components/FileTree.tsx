import { Tree, NodeRendererProps } from 'react-arborist';
import { useRef, useState, useEffect } from 'react';
import type { FileTreeNode as FileTreeNodeType } from '../lib/api/client';

interface FileTreeProps {
  nodes: FileTreeNodeType[];
  onFileSelect: (path: string) => void;
  onDirectoryExpand: (path: string) => void;
  onCreateFile: (dirPath: string) => void;
  selectedPath: string | null;
  expandedPaths: Record<string, boolean>;
}

interface ArboristNode {
  id: string;
  name: string;
  kind: 'file' | 'directory';
  children?: ArboristNode[];
}

function mapToArborist(nodes: FileTreeNodeType[]): ArboristNode[] {
  return nodes.map(n => ({
    id: n.path,
    name: n.name,
    kind: n.kind,
    children: n.kind === 'directory' ? (n.children ? mapToArborist(n.children) : []) : undefined,
  }));
}

function NodeRenderer({
  node,
  style,
  onFileSelect,
  onDirectoryExpand,
  onCreateFile,
  selectedPath,
}: NodeRendererProps<ArboristNode> & {
  onFileSelect: (path: string) => void;
  onDirectoryExpand: (path: string) => void;
  onCreateFile: (dirPath: string) => void;
  selectedPath: string | null;
}) {
  const isDirectory = node.data.kind === 'directory';
  const isSelected = !isDirectory && selectedPath === node.id;

  const handleClick = () => {
    if (isDirectory) {
      onDirectoryExpand(node.id);
      node.toggle();
    } else {
      onFileSelect(node.id);
    }
  };

  return (
    <div style={style} className="tree-node-row">
      <button
        type="button"
        className={`tree-node-btn${isSelected ? ' tree-node-btn-selected' : ''}`}
        onClick={handleClick}
      >
        {isDirectory && (
          <span className={`tree-chevron codicon codicon-chevron-${node.isOpen ? 'down' : 'right'}`} />
        )}
        <span className={`tree-icon codicon codicon-${isDirectory ? 'folder' : 'file-code'}`} />
        <span className="tree-name">{node.data.name}</span>
      </button>
      {isDirectory && (
        <button
          type="button"
          className="tree-node-add-btn"
          title={`在 ${node.data.name} 中新建文件`}
          onClick={e => { e.stopPropagation(); onCreateFile(node.id); }}
        >
          <span className="codicon codicon-plus" />
        </button>
      )}
    </div>
  );
}

export function FileTree({ nodes, onFileSelect, onDirectoryExpand, onCreateFile, selectedPath, expandedPaths }: FileTreeProps) {
  const data = mapToArborist(nodes);
  const initialOpenState = Object.fromEntries(
    Object.entries(expandedPaths).filter(([, v]) => v).map(([k]) => [k, true])
  );

  const containerRef = useRef<HTMLDivElement>(null);
  const [treeHeight, setTreeHeight] = useState(600);

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(entries => {
      const height = entries[0].contentRect.height;
      if (height > 0) setTreeHeight(height);
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  return (
    <nav className="filetree-nav" aria-label="文件浏览器">
      <div ref={containerRef} style={{ flex: 1, overflow: 'hidden', height: '100%' }}>
        <Tree<ArboristNode>
          data={data}
          openByDefault={false}
          initialOpenState={initialOpenState}
          height={treeHeight}
          indent={16}
          rowHeight={28}
          disableDrag
          disableDrop
        >
          {(props) => (
            <NodeRenderer
              {...props}
              onFileSelect={onFileSelect}
              onDirectoryExpand={onDirectoryExpand}
              onCreateFile={onCreateFile}
              selectedPath={selectedPath}
            />
          )}
        </Tree>
      </div>
    </nav>
  );
}
