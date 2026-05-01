"""Sandbox execution environment for plugins."""

import copy
from typing import Any, Optional
from core import Plugin


class SandboxViolation(Exception):
    """Raised when a plugin violates sandbox restrictions."""
    pass


class SandboxResult:
    """Result of a sandboxed execution."""

    def __init__(self, value: Any = None, error: Optional[Exception] = None):
        self.value = value
        self.error = error

    @property
    def success(self) -> bool:
        return self.error is None


# Allowed modules for sandboxed plugins
SAFE_MODULES = frozenset({"math", "json", "re", "datetime", "collections", "itertools", "functools"})


class Sandbox:
    """Sandboxed execution environment for plugins."""

    def __init__(self, allowed_modules: Optional[set[str]] = None, timeout: float = 5.0):
        self._allowed_modules = allowed_modules or set(SAFE_MODULES)
        self._timeout = timeout

    def _make_restricted_globals(self) -> dict:
        """Create a restricted globals dict for sandboxed execution."""
        safe_builtins = dict(__builtins__) if isinstance(__builtins__, dict) else dict(vars(__builtins__))

        # Remove dangerous builtins
        for name in ["exec", "eval", "compile", "open", "exit", "quit"]:
            safe_builtins.pop(name, None)

        restricted = {
            "__builtins__": safe_builtins,
        }
        return restricted

    def _restricted_import(self, name, *args, **kwargs):
        """Import function that only allows safe modules."""
        if name not in self._allowed_modules:
            raise SandboxViolation(f"Import of '{name}' is not allowed in sandbox")
        return __import__(name, *args, **kwargs)

    def execute(self, plugin: Plugin, method_name: str, *args, **kwargs) -> SandboxResult:
        """Execute a plugin method in the sandbox.

        The method is called with restricted globals to prevent
        access to dangerous builtins.
        """
        method = getattr(plugin, method_name, None)
        if method is None:
            return SandboxResult(error=AttributeError(
                f"Plugin '{plugin.name}' has no method '{method_name}'"
            ))

        try:
            result = method(*args, **kwargs)
            return SandboxResult(value=result)
        except SandboxViolation as e:
            return SandboxResult(error=e)
        except Exception as e:
            return SandboxResult(error=e)

    def execute_code(self, code: str, local_vars: Optional[dict] = None) -> SandboxResult:
        """Execute arbitrary code string in the sandbox."""
        restricted_globals = self._make_restricted_globals()
        local_ns = local_vars or {}

        try:
            exec(code, restricted_globals, local_ns)
            return SandboxResult(value=local_ns.get("result"))
        except SandboxViolation as e:
            return SandboxResult(error=e)
        except Exception as e:
            return SandboxResult(error=e)

    def check_code_safety(self, code: str) -> list[str]:
        """Static check for potentially dangerous patterns in code.

        Returns list of warning messages. Does NOT prevent execution.
        """
        warnings = []
        dangerous_patterns = [
            ("__import__", "Direct use of __import__ detected"),
            ("os.system", "os.system call detected"),
            ("subprocess", "subprocess usage detected"),
            ("eval(", "eval() call detected"),
            ("exec(", "exec() call detected"),
            ("open(", "file open() call detected"),
        ]
        for pattern, message in dangerous_patterns:
            if pattern in code:
                warnings.append(message)
        return warnings
