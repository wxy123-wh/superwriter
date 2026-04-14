from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

LAYERS = ['outline', 'plot', 'event', 'scene', 'chapter']

# Layers that participate in cascade delete (chapters are excluded)
_CASCADE_LAYERS = ['outline', 'plot', 'event', 'scene']

# Number of coords per layer
_LAYER_DEPTH = {
    'outline': 1,
    'plot': 2,
    'event': 3,
    'scene': 4,
    'chapter': 5,
}


@dataclass(frozen=True)
class NodeAddress:
    """Node address, e.g. NodeAddress('outline', ('1',)) or NodeAddress('plot', ('1', '1'))."""

    layer: str
    coords: tuple[str, ...]

    @property
    def file_name(self) -> str:
        if self.layer == 'chapter':
            return f"chapter-{'-'.join(self.coords)}.txt"
        return f"{self.layer}-{'-'.join(self.coords)}.txt"

    @property
    def parent_coords(self) -> tuple[str, ...]:
        return self.coords[:-1]

    @classmethod
    def from_file_name(cls, name: str) -> 'NodeAddress':
        stem = name.removesuffix('.txt')
        for layer in LAYERS:
            prefix = layer + '-'
            if stem.startswith(prefix):
                coords = tuple(stem[len(prefix):].split('-'))
                return cls(layer=layer, coords=coords)
        raise ValueError(f"Cannot parse node address from file name: {name!r}")


class FileStore:
    """File-system backed node store."""

    def __init__(self, root: Path) -> None:
        self._nodes = root / 'nodes'
        self._chapters = self._nodes / 'chapters'
        self._nodes.mkdir(parents=True, exist_ok=True)
        self._chapters.mkdir(parents=True, exist_ok=True)

    def _path(self, addr: NodeAddress) -> Path:
        if addr.layer == 'chapter':
            return self._chapters / addr.file_name
        return self._nodes / addr.file_name

    def read(self, addr: NodeAddress) -> str | None:
        p = self._path(addr)
        if not p.exists():
            return None
        return p.read_text(encoding='utf-8')

    def write(self, addr: NodeAddress, content: str) -> None:
        self._path(addr).write_text(content, encoding='utf-8')

    def exists(self, addr: NodeAddress) -> bool:
        return self._path(addr).exists()

    def delete(self, addr: NodeAddress, cascade: bool = True) -> list[NodeAddress]:
        """Delete a node and optionally cascade to downstream layers (not chapters)."""
        deleted: list[NodeAddress] = []

        if cascade and addr.layer in _CASCADE_LAYERS:
            layer_idx = _CASCADE_LAYERS.index(addr.layer)
            # Cascade through deeper layers in reverse order (deepest first)
            for downstream in reversed(_CASCADE_LAYERS[layer_idx + 1:]):
                prefix = '-'.join(addr.coords) + '-'
                for p in sorted(self._nodes.glob(f"{downstream}-*.txt")):
                    stem = p.stem  # e.g. "event-1-1-1"
                    coords_part = stem[len(downstream) + 1:]  # e.g. "1-1-1"
                    if coords_part.startswith(prefix):
                        child_addr = NodeAddress(layer=downstream, coords=tuple(coords_part.split('-')))
                        p.unlink()
                        deleted.append(child_addr)

        p = self._path(addr)
        if p.exists():
            p.unlink()
            deleted.append(addr)

        return deleted

    def list_layer(self, layer: str, parent_coords: tuple[str, ...] | None = None) -> list[NodeAddress]:
        """List all nodes in a layer, optionally filtered by parent coords."""
        if layer == 'chapter':
            files = sorted(self._chapters.glob('chapter-*.txt'))
        else:
            files = sorted(self._nodes.glob(f"{layer}-*.txt"))

        result: list[NodeAddress] = []
        for p in files:
            try:
                addr = NodeAddress.from_file_name(p.name)
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

    def next_coord(self, layer: str, parent_coords: tuple[str, ...]) -> str:
        """Return the next available sequence number under the given parent."""
        existing = self.list_layer(layer, parent_coords=parent_coords)
        if not existing:
            return '1'
        max_n = max(int(a.coords[-1]) for a in existing)
        return str(max_n + 1)

    def rag_sources(self) -> list[tuple[NodeAddress, str]]:
        """Return (address, content) for all nodes in the first four layers."""
        result: list[tuple[NodeAddress, str]] = []
        for layer in _CASCADE_LAYERS:
            for addr in self.list_layer(layer):
                content = self.read(addr)
                if content is not None:
                    result.append((addr, content))
        return result
