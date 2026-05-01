"""Git index (staging area) implementation."""

import time
from dataclasses import dataclass, field

from objects import Blob, ObjectStore


@dataclass
class IndexEntry:
    """A single entry in the git index."""
    path: str
    sha: str
    mode: str = "100644"
    mtime: float = field(default_factory=time.time)

    def __repr__(self):
        return f"IndexEntry({self.path!r}, {self.sha[:8]}, {self.mode})"


class Index:
    """The git index / staging area."""

    def __init__(self, object_store: ObjectStore):
        self._entries: dict[str, IndexEntry] = {}
        self._store = object_store

    def add(self, entry: IndexEntry):
        """Add or update an entry in the index."""
        self._entries[entry.path] = entry

    def remove(self, path: str) -> bool:
        """Remove an entry from the index."""
        if path in self._entries:
            del self._entries[path]
            return True
        return False

    def get(self, path: str) -> IndexEntry | None:
        """Get an entry by path."""
        return self._entries.get(path)

    def list_entries(self) -> list[IndexEntry]:
        """List all entries sorted by path."""
        return sorted(self._entries.values(), key=lambda e: e.path)

    def stage_file(self, path: str, content: bytes, mode: str = "100644") -> str:
        """Stage a file: create blob, add to index, return SHA."""
        blob = Blob(content)
        sha = self._store.save(blob)
        entry = IndexEntry(path=path, sha=sha, mode=mode)
        self.add(entry)
        return sha

    def clear(self):
        """Clear all entries."""
        self._entries.clear()

    @property
    def entry_count(self) -> int:
        return len(self._entries)
