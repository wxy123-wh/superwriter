"""
VersionStore - Manages version history for file-based nodes
Stores revisions in revisions/v1.txt, v2.txt, etc.
"""

from __future__ import annotations

from pathlib import Path


class VersionStore:
    """Manages version history for nodes."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _revisions_dir(self, node_dir: Path) -> Path:
        """Get revisions directory for a node."""
        return node_dir / "revisions"

    def save_revision(self, node_dir: Path, content: str) -> int:
        """Save current content as a new revision. Returns version number."""
        revisions_dir = self._revisions_dir(node_dir)
        revisions_dir.mkdir(parents=True, exist_ok=True)

        # Find next version number
        existing = sorted(revisions_dir.glob("v*.txt"))
        if not existing:
            version = 1
        else:
            last_version = int(existing[-1].stem[1:])  # "v3.txt" -> 3
            version = last_version + 1

        # Write revision
        revision_path = revisions_dir / f"v{version}.txt"
        revision_path.write_text(content, encoding="utf-8")

        return version

    def list_revisions(self, node_dir: Path) -> list[int]:
        """List all revision numbers for a node."""
        revisions_dir = self._revisions_dir(node_dir)
        if not revisions_dir.exists():
            return []

        versions = []
        for p in sorted(revisions_dir.glob("v*.txt")):
            try:
                version = int(p.stem[1:])  # "v3.txt" -> 3
                versions.append(version)
            except ValueError:
                continue

        return sorted(versions)

    def read_revision(self, node_dir: Path, version: int) -> str | None:
        """Read a specific revision."""
        revision_path = self._revisions_dir(node_dir) / f"v{version}.txt"
        if not revision_path.exists():
            return None
        return revision_path.read_text(encoding="utf-8")

    def restore_revision(self, node_dir: Path, version: int, current_content: str) -> tuple[str, int]:
        """
        Restore a revision as current content.
        Saves current content as new revision first.
        Returns (restored_content, new_version_number).
        """
        # Save current content as new revision
        new_version = self.save_revision(node_dir, current_content)

        # Read the target revision
        restored_content = self.read_revision(node_dir, version)
        if restored_content is None:
            raise ValueError(f"Revision v{version} not found")

        return restored_content, new_version
