"""
UnifiedFileStore - Combines file storage with version control
Uses integer coordinates like pipeline_api.py but with version history
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.storage.version_store import VersionStore


LAYERS = ['outline', 'plot', 'event', 'scene', 'chapter']

# Layers that participate in cascade delete (chapters are excluded)
_CASCADE_LAYERS = ['outline', 'plot', 'event', 'scene']


@dataclass(frozen=True)
class NodeAddress:
    """Node address with integer coordinates, e.g. NodeAddress('outline', (1,)) or NodeAddress('plot', (1, 1))."""

    layer: str
    coords: tuple[int, ...]

    def __str__(self) -> str:
        return f"{self.layer}-{'-'.join(str(c) for c in self.coords)}"

    @property
    def parent_coords(self) -> tuple[int, ...]:
        return self.coords[:-1]

    @classmethod
    def parse(cls, addr_str: str) -> 'NodeAddress':
        """Parse from string like 'plot-1-1' → NodeAddress('plot', (1, 1))."""
        for layer in LAYERS:
            prefix = layer + '-'
            if addr_str.startswith(prefix):
                rest = addr_str[len(prefix):]
                try:
                    coords = tuple(int(p) for p in rest.split('-'))
                except ValueError:
                    raise ValueError(f"Invalid node address: {addr_str!r}")
                return cls(layer=layer, coords=coords)
        raise ValueError(f"Cannot parse node address: {addr_str!r}")


class UnifiedFileStore:
    """
    Unified file store with version control.

    Directory structure:
    .superwriter/
      nodes/
        outline-1/
          content.txt          ← current content
          revisions/
            v1.txt             ← historical versions
            v2.txt
        plot-1-1/
          content.txt
          revisions/
            v1.txt
        chapters/
          chapter-1-1-1-1-1/
            content.txt
            revisions/
              v1.txt
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self._nodes_dir = root / 'nodes'
        self._chapters_dir = self._nodes_dir / 'chapters'
        self._nodes_dir.mkdir(parents=True, exist_ok=True)
        self._chapters_dir.mkdir(parents=True, exist_ok=True)

        self._version_store = VersionStore(root)

    def node_dir(self, addr: NodeAddress) -> Path:
        """Get directory for a node."""
        if addr.layer == 'chapter':
            return self._chapters_dir / f"chapter-{'-'.join(str(c) for c in addr.coords)}"
        return self._nodes_dir / f"{addr.layer}-{'-'.join(str(c) for c in addr.coords)}"

    def _content_path(self, addr: NodeAddress) -> Path:
        """Get path to content.txt for a node."""
        return self.node_dir(addr) / 'content.txt'

    def read(self, addr: NodeAddress) -> str | None:
        """Read current content of a node."""
        p = self._content_path(addr)
        if not p.exists():
            return None
        return p.read_text(encoding='utf-8')

    def write(self, addr: NodeAddress, content: str) -> None:
        """
        Write content to a node.
        Automatically saves old content as a revision before overwriting.
        """
        node_dir = self.node_dir(addr)
        content_path = self._content_path(addr)

        # If content already exists, save it as a revision
        if content_path.exists():
            old_content = content_path.read_text(encoding='utf-8')
            if old_content != content:  # Only save if content changed
                self._version_store.save_revision(node_dir, old_content)

        # Write new content
        node_dir.mkdir(parents=True, exist_ok=True)
        content_path.write_text(content, encoding='utf-8')

    def exists(self, addr: NodeAddress) -> bool:
        """Check if a node exists."""
        return self._content_path(addr).exists()

    def delete(self, addr: NodeAddress, cascade: bool = True) -> list[NodeAddress]:
        """
        Delete a node and optionally cascade to downstream layers (not chapters).
        Returns list of deleted addresses.
        """
        deleted: list[NodeAddress] = []

        if cascade and addr.layer in _CASCADE_LAYERS:
            layer_idx = _CASCADE_LAYERS.index(addr.layer)
            # Cascade through deeper layers in reverse order (deepest first)
            for downstream in reversed(_CASCADE_LAYERS[layer_idx + 1:]):
                prefix = '-'.join(str(c) for c in addr.coords) + '-'
                pattern = f"{downstream}-{prefix}*"
                for node_dir in sorted(self._nodes_dir.glob(pattern)):
                    try:
                        addr_str = node_dir.name
                        child_addr = NodeAddress.parse(addr_str)
                        # Verify it's actually a child
                        if child_addr.coords[:len(addr.coords)] == addr.coords:
                            # Delete the entire directory (content + revisions)
                            import shutil
                            shutil.rmtree(node_dir)
                            deleted.append(child_addr)
                    except (ValueError, OSError):
                        continue

        # Delete the node itself
        node_dir = self.node_dir(addr)
        if node_dir.exists():
            import shutil
            shutil.rmtree(node_dir)
            deleted.append(addr)

        return deleted

    def list_layer(self, layer: str, parent_coords: tuple[int, ...] | None = None) -> list[NodeAddress]:
        """List all nodes in a layer, optionally filtered by parent coords."""
        if layer == 'chapter':
            pattern = 'chapter-*'
            search_dir = self._chapters_dir
        else:
            pattern = f'{layer}-*'
            search_dir = self._nodes_dir

        result: list[NodeAddress] = []
        for node_dir in sorted(search_dir.glob(pattern)):
            if not node_dir.is_dir():
                continue
            try:
                addr = NodeAddress.parse(node_dir.name)
            except ValueError:
                continue

            if parent_coords is not None and addr.parent_coords != parent_coords:
                continue

            result.append(addr)

        return result

    def list_children(self, addr: NodeAddress) -> list[NodeAddress]:
        """List direct children of a node."""
        layer_idx = LAYERS.index(addr.layer)
        if layer_idx + 1 >= len(LAYERS):
            return []
        child_layer = LAYERS[layer_idx + 1]
        return self.list_layer(child_layer, parent_coords=addr.coords)

    def next_coord(self, layer: str, parent_coords: tuple[int, ...]) -> int:
        """Return the next available sequence number under the given parent."""
        existing = self.list_layer(layer, parent_coords=parent_coords)
        if not existing:
            return 1
        max_n = max(a.coords[-1] for a in existing)
        return max_n + 1

    # Version control methods

    def list_revisions(self, addr: NodeAddress) -> list[int]:
        """List all revision numbers for a node."""
        return self._version_store.list_revisions(self.node_dir(addr))

    def read_revision(self, addr: NodeAddress, version: int) -> str | None:
        """Read a specific revision of a node."""
        return self._version_store.read_revision(self.node_dir(addr), version)

    def restore_revision(self, addr: NodeAddress, version: int) -> int:
        """
        Restore a node to a specific revision.
        Current content is saved as a new revision before restoring.
        Returns the new version number of the saved current content.
        """
        current_content = self.read(addr)
        if current_content is None:
            raise ValueError(f"Node {addr} does not exist")

        restored_content, new_version = self._version_store.restore_revision(
            self.node_dir(addr), version, current_content
        )

        # Write restored content as current
        content_path = self._content_path(addr)
        content_path.write_text(restored_content, encoding='utf-8')

        return new_version

    def rag_sources(self) -> list[tuple[NodeAddress, str]]:
        """Return (address, content) for all nodes in the first four layers (for RAG indexing)."""
        result: list[tuple[NodeAddress, str]] = []
        for layer in _CASCADE_LAYERS:
            for addr in self.list_layer(layer):
                content = self.read(addr)
                if content is not None:
                    result.append((addr, content))
        return result
