"""Database migration engine with dependency resolution."""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set
from schema import SchemaVersion, VersionHistory


class MigrationError(Exception):
    """Raised when a migration fails."""
    pass


class CyclicDependencyError(MigrationError):
    """Raised when circular dependencies are detected."""
    pass


@dataclass
class Migration:
    """Represents a single database migration."""
    version: str
    description: str
    up: Callable[[], None]
    down: Callable[[], None]
    dependencies: List[str] = field(default_factory=list)

    def __hash__(self):
        return hash(self.version)

    def __eq__(self, other):
        if not isinstance(other, Migration):
            return NotImplemented
        return self.version == other.version


class MigrationEngine:
    """Engine for applying and rolling back database migrations."""

    def __init__(self):
        self._migrations: Dict[str, Migration] = {}
        self._history = VersionHistory()
        self._execution_log: List[str] = []

    @property
    def history(self) -> VersionHistory:
        return self._history

    @property
    def execution_log(self) -> List[str]:
        return list(self._execution_log)

    def register(self, migration: Migration) -> None:
        """Register a migration with the engine."""
        if migration.version in self._migrations:
            raise MigrationError(f"Migration {migration.version} already registered")
        self._migrations[migration.version] = migration

    def _detect_cycles(self, version: str, visited: Set[str], path: Set[str]) -> bool:
        """Detect cycles in the dependency graph using DFS.
        Returns True if a cycle is detected."""
        # BUG 4: Wrong cycle detection logic.
        # Uses 'visited' for both "fully processed" and "currently in path",
        # which means diamond dependencies (A->B->D, A->C->D) get flagged
        # as cycles, and some real cycles may be missed.
        if version in visited:
            return True  # BUG: doesn't distinguish "in current path" vs "fully visited"
        visited.add(version)

        migration = self._migrations.get(version)
        if migration:
            for dep in migration.dependencies:
                if dep not in self._migrations:
                    raise MigrationError(f"Unknown dependency: {dep}")
                if self._detect_cycles(dep, visited, path):
                    return True
        return False

    def _resolve_order(self, target_versions: List[str]) -> List[str]:
        """Resolve migration order respecting dependencies.
        Returns list of versions in the order they should be applied."""
        # Check for cycles first
        for version in target_versions:
            if self._detect_cycles(version, set(), set()):
                raise CyclicDependencyError(
                    f"Cyclic dependency detected involving {version}"
                )

        # Topological sort
        resolved: List[str] = []
        seen: Set[str] = set()

        def visit(ver: str):
            if ver in seen:
                return
            seen.add(ver)
            migration = self._migrations.get(ver)
            if migration:
                for dep in migration.dependencies:
                    visit(dep)
            resolved.append(ver)

        for v in target_versions:
            visit(v)

        return resolved

    def apply(self, *versions: str) -> List[str]:
        """Apply one or more migrations in dependency order.
        Returns list of successfully applied versions."""
        for v in versions:
            if v not in self._migrations:
                raise MigrationError(f"Unknown migration: {v}")

        # Filter out already applied
        pending = [v for v in versions if not self._history.is_applied(v)]
        if not pending:
            return []

        ordered = self._resolve_order(pending)
        applied: List[str] = []

        try:
            for version in ordered:
                if self._history.is_applied(version):
                    continue
                migration = self._migrations[version]
                migration.up()
                schema_ver = SchemaVersion(
                    version=version,
                    description=migration.description,
                )
                self._history.record(schema_ver)
                self._execution_log.append(f"UP: {version}")
                applied.append(version)
        except Exception as e:
            # BUG 3: On failure, rolls back ALL versions in 'ordered',
            # not just the ones in 'applied'
            self._execution_log.append(f"FAIL: {version} - {e}")
            for rollback_ver in ordered:  # BUG: should be 'applied', not 'ordered'
                rb_migration = self._migrations[rollback_ver]
                try:
                    rb_migration.down()
                    self._history.remove(SchemaVersion(
                        version=rollback_ver,
                        description=rb_migration.description,
                    ))
                    self._execution_log.append(f"ROLLBACK: {rollback_ver}")
                except Exception:
                    self._execution_log.append(f"ROLLBACK_FAIL: {rollback_ver}")
            raise MigrationError(
                f"Migration {version} failed: {e}. "
                f"Rolled back: {applied}"
            ) from e

        return applied

    def rollback(self, *versions: str) -> List[str]:
        """Rollback one or more migrations.
        Rolls back in reverse order of application.
        Returns list of successfully rolled back versions."""
        for v in versions:
            if not self._history.is_applied(v):
                raise MigrationError(f"Migration {v} is not applied")

        # BUG 2: Does not reverse the order. Migrations should be rolled
        # back in reverse application order, but this rolls them back
        # in the same order they were applied.
        to_rollback = list(versions)
        rolled_back: List[str] = []

        for version in to_rollback:
            migration = self._migrations[version]
            migration.down()
            self._history.remove(SchemaVersion(
                version=version,
                description=migration.description,
            ))
            self._execution_log.append(f"DOWN: {version}")
            rolled_back.append(version)

        return rolled_back

    def get_pending(self) -> List[str]:
        """Get list of registered but not yet applied migrations, sorted."""
        pending = [
            v for v in self._migrations
            if not self._history.is_applied(v)
        ]
        # Sort using SchemaVersion comparison (inherits BUG 1)
        pending.sort(key=lambda v: SchemaVersion(v, ""))
        return pending

    def get_applied(self) -> List[str]:
        """Get list of applied migrations in sorted order."""
        return [v.version for v in self._history.get_sorted_versions()]
