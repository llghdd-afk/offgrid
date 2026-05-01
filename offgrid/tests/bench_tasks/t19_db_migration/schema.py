"""Schema version tracking for database migration engine."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class SchemaVersion:
    """Represents a single schema version."""
    version: str
    description: str
    timestamp: datetime = field(default_factory=datetime.now)
    checksum: Optional[str] = None

    def __post_init__(self):
        parts = self.version.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError(f"Invalid version format: {self.version}. Expected 'X.Y.Z'")

    @property
    def components(self) -> tuple:
        """Return version as tuple of integers for comparison."""
        return tuple(int(x) for x in self.version.split("."))

    def __lt__(self, other: "SchemaVersion") -> bool:
        return self.version < other.version  # BUG 1: lexicographic comparison

    def __le__(self, other: "SchemaVersion") -> bool:
        return self.version <= other.version  # BUG 1: lexicographic comparison

    def __gt__(self, other: "SchemaVersion") -> bool:
        return self.version > other.version  # BUG 1: lexicographic comparison

    def __ge__(self, other: "SchemaVersion") -> bool:
        return self.version >= other.version  # BUG 1: lexicographic comparison

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SchemaVersion):
            return NotImplemented
        return self.version == other.version

    def __hash__(self) -> int:
        return hash(self.version)


class VersionHistory:
    """Tracks the history of applied schema versions."""

    def __init__(self):
        self._applied: List[SchemaVersion] = []

    def record(self, version: SchemaVersion) -> None:
        """Record a version as applied."""
        if version not in self._applied:
            self._applied.append(version)

    def remove(self, version: SchemaVersion) -> None:
        """Remove a version from history (on rollback)."""
        self._applied = [v for v in self._applied if v != version]

    def is_applied(self, version_str: str) -> bool:
        """Check if a version has been applied."""
        return any(v.version == version_str for v in self._applied)

    def get_sorted_versions(self) -> List[SchemaVersion]:
        """Return applied versions in sorted order."""
        return sorted(self._applied)

    def get_latest(self) -> Optional[SchemaVersion]:
        """Get the latest applied version."""
        if not self._applied:
            return None
        return max(self._applied)

    @property
    def count(self) -> int:
        return len(self._applied)
