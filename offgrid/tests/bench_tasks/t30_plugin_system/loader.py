"""Plugin loader - discovery, dependency resolution, and loading."""

from typing import Callable, Optional
from core import Plugin, PluginMeta, Dependency


class DependencyError(Exception):
    """Raised when dependency resolution fails."""
    pass


class PluginLoader:
    """Loads plugins with dependency resolution."""

    def __init__(self):
        self._factories: dict[str, Callable[[PluginMeta], Plugin]] = {}
        self._available: dict[str, PluginMeta] = {}

    def register_factory(self, name: str, factory: Callable[[PluginMeta], Plugin],
                         meta: Optional[PluginMeta] = None) -> None:
        """Register an in-memory plugin factory for testing."""
        self._factories[name] = factory
        if meta:
            self._available[name] = meta

    def register_meta(self, meta: PluginMeta) -> None:
        """Register plugin metadata (discovery)."""
        self._available[meta.name] = meta

    def get_available(self) -> dict[str, PluginMeta]:
        """Return all discovered plugin metadata."""
        return dict(self._available)

    def resolve_order(self, names: list[str]) -> list[str]:
        """Resolve dependency order using topological sort.

        Raises DependencyError if circular dependency detected.
        """
        order = []
        visited = set()

        def visit(name: str):
            if name in visited:
                raise DependencyError(f"Circular dependency detected involving '{name}'")
            visited.add(name)
            if name in self._available:
                for dep in self._available[name].dependencies:
                    if dep.name in self._available:
                        visit(dep.name)
            order.append(name)

        for name in names:
            if name not in visited:
                visit(name)

        return order

    def check_version_constraint(self, actual: str, constraint: str) -> bool:
        """Check if actual version satisfies the constraint.

        Supports: >=, <=, ==, >, <, and comma-separated combinations.
        """
        if not constraint:
            return True

        parts = [c.strip() for c in constraint.split(",")]
        for part in parts:
            if part.startswith(">="):
                if not (actual >= part[2:]):
                    return False
            elif part.startswith("<="):
                if not (actual <= part[2:]):
                    return False
            elif part.startswith("=="):
                if not (actual == part[2:]):
                    return False
            elif part.startswith(">"):
                if not (actual > part[1:]):
                    return False
            elif part.startswith("<"):
                if not (actual < part[1:]):
                    return False
        return True

    def load_plugin(self, name: str) -> Plugin:
        """Load a single plugin by name."""
        if name not in self._available:
            raise DependencyError(f"Plugin '{name}' not found")
        meta = self._available[name]
        if name in self._factories:
            return self._factories[name](meta)
        raise DependencyError(f"No factory registered for plugin '{name}'")

    def load_all(self, names: list[str]) -> list[Plugin]:
        """Load plugins in dependency order, checking version constraints."""
        order = self.resolve_order(names)
        loaded: dict[str, Plugin] = {}
        plugins = []

        for name in order:
            if name not in names and name not in self._available:
                continue
            meta = self._available.get(name)
            if meta:
                # Check version constraints of dependencies
                for dep in meta.dependencies:
                    if dep.name in loaded:
                        dep_version = loaded[dep.name].version
                        if not self.check_version_constraint(dep_version, dep.version_constraint):
                            raise DependencyError(
                                f"Plugin '{name}' requires '{dep.name}' {dep.version_constraint}, "
                                f"but found version {dep_version}"
                            )
            plugin = self.load_plugin(name)
            loaded[name] = plugin
            plugins.append(plugin)

        return plugins
