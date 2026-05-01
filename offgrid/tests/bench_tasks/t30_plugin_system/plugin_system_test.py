"""Tests for the plugin system: core, loader, registry, sandbox."""

import pytest
from core import Plugin, PluginMeta, PluginContext, Hook, Dependency
from loader import PluginLoader, DependencyError
from registry import PluginRegistry, PluginNotFoundError
from sandbox import Sandbox, SandboxResult, SandboxViolation, SAFE_MODULES


# ─── Test helpers ────────────────────────────────────────────────────


class SimplePlugin(Plugin):
    """A simple plugin for testing."""

    def activate(self, context: PluginContext) -> None:
        context.register_hook("on_start", lambda: f"{self.name} started", plugin_name=self.name)
        self._hooks.append("on_start")

    def deactivate(self) -> None:
        pass

    def greet(self, who: str = "world") -> str:
        return f"Hello {who} from {self.name}"


class StatefulPlugin(Plugin):
    """A plugin that maintains state."""

    def activate(self, context: PluginContext) -> None:
        context.register_hook("on_data", self._on_data, plugin_name=self.name)
        self._hooks.append("on_data")

    def deactivate(self) -> None:
        pass

    def _on_data(self, data):
        self.state.setdefault("log", []).append(data)
        return f"processed:{data}"

    def get_log(self) -> list:
        return self.state.get("log", [])


class CounterPlugin(Plugin):
    """A plugin with a counter in state, useful for reload tests."""

    def activate(self, context: PluginContext) -> None:
        context.register_hook("tick", self._tick, plugin_name=self.name)

    def deactivate(self) -> None:
        pass

    def _tick(self):
        self.state["count"] = self.state.get("count", 0) + 1
        return self.state["count"]

    def migrate_state(self, old_state: dict) -> None:
        # Migrate counter, maybe add new fields
        self.state = dict(old_state)
        self.state.setdefault("migrated", True)


class MaliciousPlugin(Plugin):
    """A plugin that tries to escape the sandbox."""

    def activate(self, context: PluginContext) -> None:
        pass

    def deactivate(self) -> None:
        pass

    def try_import_os(self) -> str:
        os_mod = __import__("os")
        return os_mod.name


def make_factory(cls):
    """Create a factory function for a plugin class."""
    return lambda meta: cls(meta)


# ─── Core tests ──────────────────────────────────────────────────────


class TestPluginContext:
    def test_register_and_call_hook(self):
        ctx = PluginContext()
        ctx.register_hook("startup", lambda: "ok", plugin_name="p1")
        results = ctx.call_hook("startup")
        assert results == ["ok"]

    def test_multiple_hooks(self):
        ctx = PluginContext()
        ctx.register_hook("event", lambda x: x * 2, plugin_name="p1")
        ctx.register_hook("event", lambda x: x + 10, plugin_name="p2")
        results = ctx.call_hook("event", 5)
        assert results == [10, 15]

    def test_call_missing_hook(self):
        ctx = PluginContext()
        assert ctx.call_hook("nonexistent") == []

    def test_services(self):
        ctx = PluginContext()
        ctx.register_service("db", {"host": "localhost"})
        assert ctx.get_service("db") == {"host": "localhost"}
        assert ctx.get_service("missing") is None

    def test_remove_hooks_for_plugin(self):
        ctx = PluginContext()
        ctx.register_hook("evt", lambda: "a", plugin_name="p1")
        ctx.register_hook("evt", lambda: "b", plugin_name="p2")
        ctx.register_hook("other", lambda: "c", plugin_name="p1")
        ctx.remove_hooks_for_plugin("p1")
        assert ctx.call_hook("evt") == ["b"]
        assert ctx.call_hook("other") == []


class TestPlugin:
    def test_basic_properties(self):
        meta = PluginMeta(name="test", version="1.0.0")
        p = Plugin(meta)
        assert p.name == "test"
        assert p.version == "1.0.0"
        assert p.state == {}

    def test_migrate_state(self):
        meta = PluginMeta(name="test", version="2.0.0")
        p = Plugin(meta)
        p.migrate_state({"key": "value", "count": 42})
        assert p.state == {"key": "value", "count": 42}


# ─── Loader tests ───────────────────────────────────────────────────


class TestDependencyResolution:
    """Tests for dependency resolution and ordering."""

    def test_no_dependencies(self):
        loader = PluginLoader()
        loader.register_meta(PluginMeta(name="A", version="1.0.0"))
        loader.register_meta(PluginMeta(name="B", version="1.0.0"))
        order = loader.resolve_order(["A", "B"])
        assert set(order) == {"A", "B"}

    def test_simple_chain(self):
        """A depends on B, B depends on C -> load order: C, B, A."""
        loader = PluginLoader()
        loader.register_meta(PluginMeta(name="A", version="1.0.0",
                                        dependencies=[Dependency("B")]))
        loader.register_meta(PluginMeta(name="B", version="1.0.0",
                                        dependencies=[Dependency("C")]))
        loader.register_meta(PluginMeta(name="C", version="1.0.0"))
        order = loader.resolve_order(["A"])
        assert order == ["C", "B", "A"]

    def test_diamond_dependency(self):
        """Diamond: A->B, A->C, B->D, C->D. Should NOT be a cycle."""
        loader = PluginLoader()
        loader.register_meta(PluginMeta(name="A", version="1.0.0",
                                        dependencies=[Dependency("B"), Dependency("C")]))
        loader.register_meta(PluginMeta(name="B", version="1.0.0",
                                        dependencies=[Dependency("D")]))
        loader.register_meta(PluginMeta(name="C", version="1.0.0",
                                        dependencies=[Dependency("D")]))
        loader.register_meta(PluginMeta(name="D", version="1.0.0"))
        order = loader.resolve_order(["A"])
        # D must come before B and C, which must come before A
        assert order.index("D") < order.index("B")
        assert order.index("D") < order.index("C")
        assert order.index("B") < order.index("A")
        assert order.index("C") < order.index("A")

    def test_true_circular_dependency(self):
        """A->B->C->A is a real cycle."""
        loader = PluginLoader()
        loader.register_meta(PluginMeta(name="A", version="1.0.0",
                                        dependencies=[Dependency("B")]))
        loader.register_meta(PluginMeta(name="B", version="1.0.0",
                                        dependencies=[Dependency("C")]))
        loader.register_meta(PluginMeta(name="C", version="1.0.0",
                                        dependencies=[Dependency("A")]))
        with pytest.raises(DependencyError, match="[Cc]ircular"):
            loader.resolve_order(["A"])

    def test_self_dependency(self):
        """A depends on itself."""
        loader = PluginLoader()
        loader.register_meta(PluginMeta(name="A", version="1.0.0",
                                        dependencies=[Dependency("A")]))
        with pytest.raises(DependencyError, match="[Cc]ircular"):
            loader.resolve_order(["A"])

    def test_complex_diamond_no_false_positive(self):
        """Larger diamond: E->B, E->C, B->A, C->A, C->D, D->A.
        A is reachable via multiple paths. Not a cycle."""
        loader = PluginLoader()
        loader.register_meta(PluginMeta(name="E", version="1.0.0",
                                        dependencies=[Dependency("B"), Dependency("C")]))
        loader.register_meta(PluginMeta(name="B", version="1.0.0",
                                        dependencies=[Dependency("A")]))
        loader.register_meta(PluginMeta(name="C", version="1.0.0",
                                        dependencies=[Dependency("A"), Dependency("D")]))
        loader.register_meta(PluginMeta(name="D", version="1.0.0",
                                        dependencies=[Dependency("A")]))
        loader.register_meta(PluginMeta(name="A", version="1.0.0"))
        order = loader.resolve_order(["E"])
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("A") < order.index("D")
        assert order.index("B") < order.index("E")
        assert order.index("C") < order.index("E")


class TestVersionConstraints:
    """Tests for semantic version constraint checking."""

    def test_no_constraint(self):
        loader = PluginLoader()
        assert loader.check_version_constraint("1.0.0", "") is True

    def test_exact_match(self):
        loader = PluginLoader()
        assert loader.check_version_constraint("1.2.3", "==1.2.3") is True
        assert loader.check_version_constraint("1.2.4", "==1.2.3") is False

    def test_gte(self):
        loader = PluginLoader()
        assert loader.check_version_constraint("1.2.0", ">=1.2.0") is True
        assert loader.check_version_constraint("2.0.0", ">=1.2.0") is True
        assert loader.check_version_constraint("1.1.0", ">=1.2.0") is False

    def test_numeric_comparison_not_lexicographic(self):
        """1.10.0 should be > 1.2.0 (numeric), not < (lexicographic)."""
        loader = PluginLoader()
        assert loader.check_version_constraint("1.10.0", ">=1.2.0") is True
        assert loader.check_version_constraint("1.2.0", ">=1.10.0") is False

    def test_less_than(self):
        loader = PluginLoader()
        assert loader.check_version_constraint("1.0.0", "<2.0.0") is True
        assert loader.check_version_constraint("2.0.0", "<2.0.0") is False

    def test_combined_constraints(self):
        """Range: >=1.0.0,<2.0.0"""
        loader = PluginLoader()
        assert loader.check_version_constraint("1.5.0", ">=1.0.0,<2.0.0") is True
        assert loader.check_version_constraint("0.9.0", ">=1.0.0,<2.0.0") is False
        assert loader.check_version_constraint("2.0.0", ">=1.0.0,<2.0.0") is False

    def test_numeric_less_than(self):
        """1.9.0 < 1.10.0 numerically (but not lexicographically)."""
        loader = PluginLoader()
        assert loader.check_version_constraint("1.9.0", "<1.10.0") is True
        assert loader.check_version_constraint("1.11.0", "<1.10.0") is False


class TestPluginLoading:
    """Tests for full plugin loading pipeline."""

    def test_load_single_plugin(self):
        loader = PluginLoader()
        meta = PluginMeta(name="greeter", version="1.0.0")
        loader.register_meta(meta)
        loader.register_factory("greeter", make_factory(SimplePlugin), meta)
        plugin = loader.load_plugin("greeter")
        assert plugin.name == "greeter"

    def test_load_all_with_deps(self):
        loader = PluginLoader()
        meta_a = PluginMeta(name="A", version="1.0.0",
                            dependencies=[Dependency("B", ">=1.0.0")])
        meta_b = PluginMeta(name="B", version="1.5.0")
        loader.register_meta(meta_a)
        loader.register_meta(meta_b)
        loader.register_factory("A", make_factory(SimplePlugin), meta_a)
        loader.register_factory("B", make_factory(SimplePlugin), meta_b)
        plugins = loader.load_all(["A", "B"])
        names = [p.name for p in plugins]
        assert names.index("B") < names.index("A")

    def test_load_fails_version_constraint(self):
        loader = PluginLoader()
        meta_a = PluginMeta(name="A", version="1.0.0",
                            dependencies=[Dependency("B", ">=2.0.0")])
        meta_b = PluginMeta(name="B", version="1.5.0")
        loader.register_meta(meta_a)
        loader.register_meta(meta_b)
        loader.register_factory("A", make_factory(SimplePlugin), meta_a)
        loader.register_factory("B", make_factory(SimplePlugin), meta_b)
        with pytest.raises(DependencyError, match="requires"):
            loader.load_all(["A", "B"])

    def test_load_not_found(self):
        loader = PluginLoader()
        with pytest.raises(DependencyError, match="not found"):
            loader.load_plugin("nonexistent")


# ─── Registry tests ─────────────────────────────────────────────────


class TestRegistry:
    """Tests for the plugin registry."""

    def test_register_and_get(self):
        registry = PluginRegistry()
        meta = PluginMeta(name="test", version="1.0.0")
        plugin = SimplePlugin(meta)
        registry.register(plugin)
        assert registry.get("test") is plugin
        assert registry.has("test")

    def test_get_all_preserves_order(self):
        registry = PluginRegistry()
        for name in ["alpha", "beta", "gamma"]:
            registry.register(SimplePlugin(PluginMeta(name=name, version="1.0.0")))
        names = [p.name for p in registry.get_all()]
        assert names == ["alpha", "beta", "gamma"]

    def test_unregister(self):
        registry = PluginRegistry()
        meta = PluginMeta(name="test", version="1.0.0")
        plugin = SimplePlugin(meta)
        registry.register(plugin)
        removed = registry.unregister("test")
        assert removed is plugin
        assert not registry.has("test")
        with pytest.raises(PluginNotFoundError):
            registry.get("test")

    def test_unregister_not_found(self):
        registry = PluginRegistry()
        with pytest.raises(PluginNotFoundError):
            registry.unregister("ghost")

    def test_hooks_cleaned_after_unregister(self):
        """After unregistering a plugin, its hooks must be removed."""
        registry = PluginRegistry()
        ctx = registry.context

        p1 = SimplePlugin(PluginMeta(name="p1", version="1.0.0"))
        p2 = SimplePlugin(PluginMeta(name="p2", version="1.0.0"))
        registry.register(p1)
        registry.register(p2)

        # Both plugins register "on_start" hook
        results_before = ctx.call_hook("on_start")
        assert len(results_before) == 2

        # Unregister p1 — its hooks should be removed
        registry.unregister("p1")
        results_after = ctx.call_hook("on_start")
        assert len(results_after) == 1
        assert "p2" in results_after[0]
        assert "p1" not in str(results_after)

    def test_hook_no_stale_callback_after_unload(self):
        """More specific: after unregistering, calling hooks must not trigger
        the unloaded plugin's callbacks (which may reference freed state)."""
        registry = PluginRegistry()
        ctx = registry.context

        stateful = StatefulPlugin(PluginMeta(name="stateful", version="1.0.0"))
        registry.register(stateful)

        # Hook works while registered
        ctx.call_hook("on_data", "hello")
        assert stateful.get_log() == ["hello"]

        registry.unregister("stateful")

        # After unregister, hook should NOT call the old callback
        results = ctx.call_hook("on_data", "ghost")
        assert results == []  # No callbacks should fire


class TestHotReload:
    """Tests for hot-reloading plugins."""

    def test_reload_preserves_state(self):
        """Hot reload should migrate state from old to new plugin."""
        registry = PluginRegistry()
        ctx = registry.context

        old_plugin = CounterPlugin(PluginMeta(name="counter", version="1.0.0"))
        registry.register(old_plugin)

        # Build up some state
        ctx.call_hook("tick")
        ctx.call_hook("tick")
        ctx.call_hook("tick")
        assert old_plugin.state["count"] == 3

        # Hot-reload with new version
        new_plugin = CounterPlugin(PluginMeta(name="counter", version="2.0.0"))
        registry.reload_plugin("counter", new_plugin)

        # New plugin should have migrated state
        assert new_plugin.state.get("count") == 3
        assert new_plugin.state.get("migrated") is True

    def test_reload_updates_version(self):
        registry = PluginRegistry()
        old = SimplePlugin(PluginMeta(name="p", version="1.0.0"))
        registry.register(old)
        assert registry.get("p").version == "1.0.0"

        new = SimplePlugin(PluginMeta(name="p", version="2.0.0"))
        registry.reload_plugin("p", new)
        assert registry.get("p").version == "2.0.0"

    def test_reload_hooks_are_fresh(self):
        """After reload, only the new plugin's hooks should be active."""
        registry = PluginRegistry()
        ctx = registry.context

        old = SimplePlugin(PluginMeta(name="reloader", version="1.0.0"))
        registry.register(old)

        hook_results = ctx.call_hook("on_start")
        assert len(hook_results) == 1

        new = SimplePlugin(PluginMeta(name="reloader", version="2.0.0"))
        registry.reload_plugin("reloader", new)

        # Should have exactly 1 hook (from new), not 2 (old + new)
        hook_results = ctx.call_hook("on_start")
        assert len(hook_results) == 1
        assert "reloader" in hook_results[0]


# ─── Sandbox tests ──────────────────────────────────────────────────


class TestSandbox:
    """Tests for sandbox execution."""

    def test_execute_method(self):
        sandbox = Sandbox()
        meta = PluginMeta(name="greeter", version="1.0.0")
        plugin = SimplePlugin(meta)
        result = sandbox.execute(plugin, "greet", "Alice")
        assert result.success
        assert result.value == "Hello Alice from greeter"

    def test_execute_missing_method(self):
        sandbox = Sandbox()
        meta = PluginMeta(name="test", version="1.0.0")
        plugin = SimplePlugin(meta)
        result = sandbox.execute(plugin, "nonexistent")
        assert not result.success
        assert isinstance(result.error, AttributeError)

    def test_execute_safe_code(self):
        sandbox = Sandbox()
        result = sandbox.execute_code("import math\nresult = math.sqrt(16)")
        assert result.success
        assert result.value == 4.0

    def test_dangerous_builtins_removed(self):
        """exec, eval, compile, open should be removed."""
        sandbox = Sandbox()
        result = sandbox.execute_code("result = open('/etc/passwd', 'r')")
        assert not result.success

    def test_import_os_blocked(self):
        """__import__('os') should be blocked in sandbox."""
        sandbox = Sandbox()
        # Try to escape via __import__
        result = sandbox.execute_code("result = __import__('os').getcwd()")
        assert not result.success, (
            "Sandbox should block __import__('os') but it succeeded"
        )

    def test_import_subprocess_blocked(self):
        """Another escape attempt via __import__."""
        sandbox = Sandbox()
        result = sandbox.execute_code("result = __import__('subprocess').run(['echo', 'pwned'])")
        assert not result.success

    def test_allowed_imports_work(self):
        """Safe modules should be importable."""
        sandbox = Sandbox()
        result = sandbox.execute_code("import json\nresult = json.dumps({'a': 1})")
        assert result.success
        assert result.value == '{"a": 1}'

    def test_check_code_safety(self):
        sandbox = Sandbox()
        warnings = sandbox.check_code_safety("import os\nos.system('rm -rf /')")
        assert any("os.system" in w for w in warnings)

        clean_warnings = sandbox.check_code_safety("x = 1 + 2")
        assert clean_warnings == []

    def test_custom_allowed_modules(self):
        sandbox = Sandbox(allowed_modules={"math"})
        # math should be allowed
        result = sandbox.execute_code("import math\nresult = math.pi")
        assert result.success

    def test_sandbox_result_properties(self):
        r1 = SandboxResult(value=42)
        assert r1.success
        assert r1.value == 42

        r2 = SandboxResult(error=RuntimeError("boom"))
        assert not r2.success
        assert r2.value is None


# ─── Integration tests ──────────────────────────────────────────────


class TestIntegration:
    """End-to-end integration tests combining all components."""

    def test_full_lifecycle(self):
        """Load -> register -> use -> unregister lifecycle."""
        loader = PluginLoader()
        meta = PluginMeta(name="lifecycle", version="1.0.0")
        loader.register_meta(meta)
        loader.register_factory("lifecycle", make_factory(StatefulPlugin), meta)

        plugins = loader.load_all(["lifecycle"])
        assert len(plugins) == 1

        registry = PluginRegistry()
        registry.register(plugins[0])

        ctx = registry.context
        ctx.call_hook("on_data", "test_event")
        assert plugins[0].get_log() == ["test_event"]

        registry.unregister("lifecycle")
        assert not registry.has("lifecycle")

        # Hook should not fire after unregister
        results = ctx.call_hook("on_data", "after_unregister")
        assert results == []

    def test_diamond_deps_with_version_check(self):
        """Integration: diamond dependency graph + version constraints."""
        loader = PluginLoader()

        meta_core = PluginMeta(name="core_lib", version="1.10.0")
        meta_ui = PluginMeta(name="ui", version="2.0.0",
                             dependencies=[Dependency("core_lib", ">=1.2.0")])
        meta_api = PluginMeta(name="api", version="1.0.0",
                              dependencies=[Dependency("core_lib", ">=1.5.0")])
        meta_app = PluginMeta(name="app", version="1.0.0",
                              dependencies=[Dependency("ui", ">=1.0.0"),
                                            Dependency("api", ">=1.0.0")])

        for meta in [meta_core, meta_ui, meta_api, meta_app]:
            loader.register_meta(meta)
            loader.register_factory(meta.name, make_factory(SimplePlugin), meta)

        # Should resolve diamond without false cycle detection
        plugins = loader.load_all(["app", "ui", "api", "core_lib"])
        names = [p.name for p in plugins]
        assert names.index("core_lib") < names.index("ui")
        assert names.index("core_lib") < names.index("api")
        assert names.index("ui") < names.index("app")
        assert names.index("api") < names.index("app")

    def test_reload_with_sandbox(self):
        """Hot reload a plugin and verify state migration + sandbox still works."""
        registry = PluginRegistry()
        ctx = registry.context
        sandbox = Sandbox()

        old = CounterPlugin(PluginMeta(name="counter", version="1.0.0"))
        registry.register(old)

        # Accumulate state via hooks
        ctx.call_hook("tick")
        ctx.call_hook("tick")
        assert old.state["count"] == 2

        # Reload
        new = CounterPlugin(PluginMeta(name="counter", version="1.1.0"))
        registry.reload_plugin("counter", new)

        # State should be migrated
        current = registry.get("counter")
        assert current.state.get("count") == 2
        assert current.version == "1.1.0"

        # Continue ticking
        ctx.call_hook("tick")
        assert current.state["count"] == 3

    def test_version_constraint_numeric_in_load(self):
        """Ensure version constraints use numeric (not lexicographic) comparison
        during actual plugin loading."""
        loader = PluginLoader()
        meta_dep = PluginMeta(name="dep", version="1.10.0")
        meta_main = PluginMeta(name="main", version="1.0.0",
                               dependencies=[Dependency("dep", ">=1.2.0")])
        loader.register_meta(meta_dep)
        loader.register_meta(meta_main)
        loader.register_factory("dep", make_factory(SimplePlugin), meta_dep)
        loader.register_factory("main", make_factory(SimplePlugin), meta_main)

        # 1.10.0 >= 1.2.0 is True numerically but False lexicographically
        plugins = loader.load_all(["main", "dep"])
        assert len(plugins) == 2
