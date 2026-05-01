"""Plugin system core interfaces."""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Dependency:
    """A plugin dependency specification."""
    name: str
    version_constraint: str = ""  # e.g. ">=1.2.0", "==2.0.0", ">=1.0.0,<2.0.0"


@dataclass
class PluginMeta:
    """Metadata describing a plugin before loading."""
    name: str
    version: str
    module_path: str = ""  # file path or module name
    dependencies: list[Dependency] = field(default_factory=list)


class Plugin:
    """Base class for all plugins."""

    def __init__(self, meta: PluginMeta):
        self.meta = meta
        self.state: dict[str, Any] = {}
        self._hooks: list[str] = []  # hook names this plugin registered

    @property
    def name(self) -> str:
        return self.meta.name

    @property
    def version(self) -> str:
        return self.meta.version

    def activate(self, context: "PluginContext") -> None:
        """Called when the plugin is activated."""
        pass

    def deactivate(self) -> None:
        """Called when the plugin is deactivated."""
        pass

    def migrate_state(self, old_state: dict[str, Any]) -> None:
        """Migrate state from a previous version during hot reload."""
        self.state = dict(old_state)


@dataclass
class Hook:
    """A named hook with a callback."""
    name: str
    callback: Callable[..., Any]
    plugin_name: str = ""


class PluginContext:
    """Context provided to plugins for interacting with the system."""

    def __init__(self):
        self._hooks: dict[str, list[Hook]] = {}
        self._services: dict[str, Any] = {}

    def register_hook(self, hook_name: str, callback: Callable, plugin_name: str = "") -> None:
        """Register a callback for a named hook."""
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        self._hooks[hook_name].append(Hook(
            name=hook_name,
            callback=callback,
            plugin_name=plugin_name,
        ))

    def call_hook(self, hook_name: str, *args, **kwargs) -> list[Any]:
        """Call all callbacks registered for a hook, return list of results."""
        results = []
        for hook in self._hooks.get(hook_name, []):
            results.append(hook.callback(*args, **kwargs))
        return results

    def register_service(self, name: str, service: Any) -> None:
        """Register a named service."""
        self._services[name] = service

    def get_service(self, name: str) -> Optional[Any]:
        """Get a registered service by name."""
        return self._services.get(name)

    def remove_hooks_for_plugin(self, plugin_name: str) -> None:
        """Remove all hooks registered by a specific plugin."""
        for hook_name in list(self._hooks.keys()):
            self._hooks[hook_name] = [
                h for h in self._hooks[hook_name] if h.plugin_name != plugin_name
            ]
            if not self._hooks[hook_name]:
                del self._hooks[hook_name]
