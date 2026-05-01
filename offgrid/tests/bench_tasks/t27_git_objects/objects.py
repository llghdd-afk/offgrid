"""Git object model: blob, tree, commit objects and object store."""

import hashlib
import os
import zlib


class GitObject:
    """Base class for git objects."""

    obj_type = None  # subclasses override

    def __init__(self, content: bytes = b""):
        self.content = content

    @property
    def sha(self) -> str:
        """Compute SHA1 hash using git's object format: 'type len\0content'."""
        header = f"{self.obj_type} {len(self.content)} ".encode()
        return hashlib.sha1(header + self.content).hexdigest()

    def serialize(self) -> bytes:
        """Serialize object for storage."""
        header = f"{self.obj_type} {len(self.content)}\0".encode()
        return zlib.compress(header + self.content)

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.sha[:8]}>"


class Blob(GitObject):
    """A blob stores file content."""

    obj_type = "blob"

    def __init__(self, data: bytes):
        super().__init__(data)

    @property
    def data(self) -> bytes:
        return self.content


class TreeEntry:
    """A single entry in a tree object."""

    def __init__(self, mode: str, name: str, sha: str):
        self.mode = mode
        self.name = name
        self.sha = sha

    def __repr__(self):
        return f"TreeEntry({self.mode}, {self.name!r}, {self.sha[:8]})"


class Tree(GitObject):
    """A tree stores directory listings."""

    obj_type = "tree"

    def __init__(self, entries: list[TreeEntry] = None):
        self._entries = entries or []
        super().__init__(self._build_content())

    def _sort_key(self, entry: TreeEntry) -> str:
        """Sort key for tree entries.
        Git sorts tree entries by name. Directories (mode 40000)
        are treated specially for sorting purposes.
        """
        return entry.name

    def _build_content(self) -> bytes:
        """Build the binary content of the tree object."""
        self._entries.sort(key=self._sort_key)
        result = b""
        for entry in self._entries:
            sha_bytes = entry.sha.encode("ascii")
            result += f"{entry.mode} {entry.name}\0".encode() + sha_bytes
        return result

    @property
    def entries(self) -> list[TreeEntry]:
        return list(self._entries)

    def add_entry(self, entry: TreeEntry):
        self._entries.append(entry)
        self.content = self._build_content()


class Commit(GitObject):
    """A commit object."""

    obj_type = "commit"

    def __init__(self, tree_sha: str, parent_shas: list[str] = None,
                 author: str = "Test User <test@example.com>",
                 message: str = ""):
        self.tree_sha = tree_sha
        self.parent_shas = parent_shas or []
        self.author = author
        self.message = message
        super().__init__(self._build_content())

    def _build_content(self) -> bytes:
        lines = [f"tree {self.tree_sha}"]
        for parent in self.parent_shas:
            lines.append(f"parent {parent}")
        lines.append(f"author {self.author}")
        lines.append(f"committer {self.author}")
        lines.append("")
        lines.append(self.message)
        return "\n".join(lines).encode()


class ObjectStore:
    """In-memory git object store keyed by SHA."""

    def __init__(self):
        self._objects: dict[str, GitObject] = {}

    def save(self, obj: GitObject) -> str:
        """Store an object and return its SHA."""
        sha = obj.sha
        self._objects[sha] = obj
        return sha

    def load(self, sha: str) -> GitObject | None:
        """Load an object by SHA."""
        return self._objects.get(sha)

    def contains(self, sha: str) -> bool:
        return sha in self._objects

    def all_objects(self) -> list[GitObject]:
        return list(self._objects.values())
