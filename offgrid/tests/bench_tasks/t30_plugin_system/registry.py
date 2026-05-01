"""Plugin registry - central management of loaded plugins."""

from typing import Optional
from core import Plugin, PluginContext


class PluginNotFoundError(Exception):
    """Raised when a plugin is not found in the registry."""
    pass


class PluginRegistry:
    """Central registry for managing loaded plugins."""

    def __init__(self, context: Optional[PluginContext] = None):
        self._plugins: dict[str, Plugin] = {}
        self._context = context or PluginContext()
        self._load_order: list[str] = []

    @property
    def context(self) -> PluginContext:
        return self._context

    def register(self, plugin: Plugin) -> None:
        """Register and activate a plugin."""
        self._plugins[plugin.name] = plugin
        self._load_order.append(plugin.name)
        plugin.activate(self._context)

    def unregister(self, name: str) -> Plugin:
        """Unregister a plugin by name."""
        if name not in self._plugins:
            raise PluginNotFoundError(f"Plugin '{name}' not found")
        plugin = self._plugins.pop(name)
        if name in self._load_order:
            self._load_order.remove(name)
        plugin.deactivate()
        return plugin

    def get(self, name: str) -> Plugin:
        """Get a registered plugin by name."""
        if name not in self._plugins:
            raise PluginNotFoundError(f"Plugin '{name}' not found")
        return self._plugins[name]

    def get_all(self) -> list[Plugin]:
        """Get all registered plugins in load order."""
        return [self._plugins[name] for name in self._load_order if name in self._plugins]

    def has(self, name: str) -> bool:
        """Check if a plugin is registered."""
        return name in self._plugins

    def reload_plugin(self, name: str, new_plugin: Plugin) -> Plugin:
        """Hot-reload a plugin: unregister old, register new."""
        old_plugin = self.unregister(name)
        self.register(new_plugin)
        return old_plugin
