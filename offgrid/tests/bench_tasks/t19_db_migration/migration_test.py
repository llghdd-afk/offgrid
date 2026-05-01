"""Tests for database migration engine.

DO NOT MODIFY THIS FILE. Fix the bugs in migration.py and schema.py.
"""

import pytest
from schema import SchemaVersion, VersionHistory
from migration import (
    Migration,
    MigrationEngine,
    MigrationError,
    CyclicDependencyError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_migration(version: str, deps=None, up_effect=None, down_effect=None,
                   fail_up=False, desc=None):
    """Create a Migration with trackable side effects."""
    log = []

    def up():
        if fail_up:
            raise RuntimeError(f"Migration {version} failed!")
        if up_effect is not None:
            up_effect()
        log.append(f"up:{version}")

    def down():
        if down_effect is not None:
            down_effect()
        log.append(f"down:{version}")

    m = Migration(
        version=version,
        description=desc or f"Migration {version}",
        up=up,
        down=down,
        dependencies=deps or [],
    )
    return m, log


# ===========================================================================
# BUG 1 — Version sorting must be semantic, not lexicographic
# ===========================================================================

class TestVersionSorting:
    """SchemaVersion comparison must use numeric version components."""

    def test_basic_ordering(self):
        v1 = SchemaVersion("1.0.0", "first")
        v2 = SchemaVersion("2.0.0", "second")
        assert v1 < v2
        assert v2 > v1

    def test_semantic_vs_lexicographic(self):
        """1.2.0 < 1.10.0 numerically, but '1.2.0' > '1.10.0' lexicographically."""
        v2 = SchemaVersion("1.2.0", "minor two")
        v10 = SchemaVersion("1.10.0", "minor ten")
        assert v2 < v10, "1.2.0 should be less than 1.10.0 (semantic order)"
        assert v10 > v2

    def test_semantic_sort_list(self):
        versions = [
            SchemaVersion("1.10.0", "ten"),
            SchemaVersion("1.2.0", "two"),
            SchemaVersion("1.1.0", "one"),
            SchemaVersion("2.0.0", "major"),
        ]
        result = sorted(versions)
        assert [v.version for v in result] == [
            "1.1.0", "1.2.0", "1.10.0", "2.0.0"
        ]

    def test_latest_version_semantic(self):
        history = VersionHistory()
        history.record(SchemaVersion("1.2.0", "a"))
        history.record(SchemaVersion("1.10.0", "b"))
        latest = history.get_latest()
        assert latest is not None
        assert latest.version == "1.10.0"

    def test_sorted_versions_semantic(self):
        history = VersionHistory()
        history.record(SchemaVersion("1.10.0", "b"))
        history.record(SchemaVersion("1.2.0", "a"))
        history.record(SchemaVersion("1.1.0", "c"))
        ordered = history.get_sorted_versions()
        assert [v.version for v in ordered] == ["1.1.0", "1.2.0", "1.10.0"]

    def test_engine_pending_sorted_semantically(self):
        engine = MigrationEngine()
        for v in ["1.10.0", "1.2.0", "1.1.0", "2.0.0"]:
            m, _ = make_migration(v)
            engine.register(m)
        pending = engine.get_pending()
        assert pending == ["1.1.0", "1.2.0", "1.10.0", "2.0.0"]

    def test_engine_applied_sorted_semantically(self):
        engine = MigrationEngine()
        for v in ["1.10.0", "1.2.0", "1.1.0"]:
            m, _ = make_migration(v)
            engine.register(m)
        engine.apply("1.10.0", "1.2.0", "1.1.0")
        applied = engine.get_applied()
        assert applied == ["1.1.0", "1.2.0", "1.10.0"]


# ===========================================================================
# BUG 2 — Rollback must happen in reverse application order
# ===========================================================================

class TestRollbackOrder:
    """Rollback should undo migrations in reverse order."""

    def test_rollback_single(self):
        engine = MigrationEngine()
        m1, log1 = make_migration("1.0.0")
        engine.register(m1)
        engine.apply("1.0.0")
        engine.rollback("1.0.0")
        assert not engine.history.is_applied("1.0.0")

    def test_rollback_reverse_order(self):
        """When rolling back [1.0.0, 2.0.0, 3.0.0] the down() calls
        must execute in order 3.0.0 → 2.0.0 → 1.0.0."""
        order = []
        engine = MigrationEngine()

        for v in ["1.0.0", "2.0.0", "3.0.0"]:
            m = Migration(
                version=v,
                description=f"m-{v}",
                up=lambda: None,
                down=(lambda ver: lambda: order.append(ver))(v),
                dependencies=[],
            )
            engine.register(m)

        engine.apply("1.0.0", "2.0.0", "3.0.0")
        engine.rollback("1.0.0", "2.0.0", "3.0.0")

        assert order == ["3.0.0", "2.0.0", "1.0.0"], (
            f"Rollback order should be reverse, got {order}"
        )

    def test_rollback_partial(self):
        """Rolling back only the last two should reverse just those."""
        order = []
        engine = MigrationEngine()

        for v in ["1.0.0", "2.0.0", "3.0.0"]:
            m = Migration(
                version=v,
                description=f"m-{v}",
                up=lambda: None,
                down=(lambda ver: lambda: order.append(ver))(v),
                dependencies=[],
            )
            engine.register(m)

        engine.apply("1.0.0", "2.0.0", "3.0.0")
        engine.rollback("2.0.0", "3.0.0")

        assert order == ["3.0.0", "2.0.0"]
        assert engine.history.is_applied("1.0.0")


# ===========================================================================
# BUG 3 — Partial failure must only rollback actually-applied migrations
# ===========================================================================

class TestPartialFailure:
    """When a batch apply fails mid-way, only rollback what was applied."""

    def test_fail_mid_batch_rollback_scope(self):
        """If 3rd migration fails, only the first 2 should be rolled back."""
        rolled = []
        engine = MigrationEngine()

        m1 = Migration("1.0.0", "m1", up=lambda: None,
                        down=lambda: rolled.append("1.0.0"))
        m2 = Migration("2.0.0", "m2", up=lambda: None,
                        down=lambda: rolled.append("2.0.0"))

        def bad_up():
            raise RuntimeError("boom")

        m3 = Migration("3.0.0", "m3", up=bad_up,
                        down=lambda: rolled.append("3.0.0"))

        engine.register(m1)
        engine.register(m2)
        engine.register(m3)

        with pytest.raises(MigrationError):
            engine.apply("1.0.0", "2.0.0", "3.0.0")

        # Only 1.0.0 and 2.0.0 should have been rolled back
        assert "1.0.0" in rolled
        assert "2.0.0" in rolled
        assert "3.0.0" not in rolled, (
            "Migration 3.0.0 was never applied — should not be rolled back"
        )

    def test_fail_first_migration_no_rollback(self):
        """If the very first migration fails, nothing should be rolled back."""
        rolled = []

        def bad_up():
            raise RuntimeError("boom")

        engine = MigrationEngine()
        m1 = Migration("1.0.0", "m1", up=bad_up,
                        down=lambda: rolled.append("1.0.0"))
        engine.register(m1)

        with pytest.raises(MigrationError):
            engine.apply("1.0.0")

        assert rolled == [], "Nothing was applied, nothing should be rolled back"

    def test_fail_mid_batch_state_clean(self):
        """After failed batch, history should be clean (no applied versions)."""
        engine = MigrationEngine()
        m1, _ = make_migration("1.0.0")
        m2, _ = make_migration("2.0.0", fail_up=True)
        engine.register(m1)
        engine.register(m2)

        with pytest.raises(MigrationError):
            engine.apply("1.0.0", "2.0.0")

        assert not engine.history.is_applied("1.0.0")
        assert not engine.history.is_applied("2.0.0")


# ===========================================================================
# BUG 4 — Cycle detection must handle diamond dependencies correctly
# ===========================================================================

class TestCycleDetection:
    """DFS cycle detection must distinguish visiting vs visited nodes."""

    def test_diamond_dependency_is_not_cycle(self):
        """Diamond: A->B->D, A->C->D. This is NOT a cycle."""
        engine = MigrationEngine()
        md, _ = make_migration("1.0.0")                           # D
        mb, _ = make_migration("2.0.0", deps=["1.0.0"])           # B -> D
        mc, _ = make_migration("3.0.0", deps=["1.0.0"])           # C -> D
        ma, _ = make_migration("4.0.0", deps=["2.0.0", "3.0.0"]) # A -> B, C

        engine.register(md)
        engine.register(mb)
        engine.register(mc)
        engine.register(ma)

        # Should NOT raise — diamond is valid
        result = engine.apply("4.0.0")
        assert "1.0.0" in result
        assert "4.0.0" in result

    def test_real_cycle_detected(self):
        """A->B->C->A is a real cycle and must raise."""
        engine = MigrationEngine()
        ma, _ = make_migration("1.0.0", deps=["3.0.0"])
        mb, _ = make_migration("2.0.0", deps=["1.0.0"])
        mc, _ = make_migration("3.0.0", deps=["2.0.0"])

        engine.register(ma)
        engine.register(mb)
        engine.register(mc)

        with pytest.raises(CyclicDependencyError):
            engine.apply("1.0.0")

    def test_self_cycle_detected(self):
        """A migration depending on itself is a cycle."""
        engine = MigrationEngine()
        m, _ = make_migration("1.0.0", deps=["1.0.0"])
        engine.register(m)

        with pytest.raises(CyclicDependencyError):
            engine.apply("1.0.0")

    def test_complex_diamond_no_cycle(self):
        """Larger diamond with shared deps should not be flagged."""
        engine = MigrationEngine()
        #     5.0.0
        #    /     \
        # 3.0.0  4.0.0
        #    \     /
        #     2.0.0
        #       |
        #     1.0.0
        m1, _ = make_migration("1.0.0")
        m2, _ = make_migration("2.0.0", deps=["1.0.0"])
        m3, _ = make_migration("3.0.0", deps=["2.0.0"])
        m4, _ = make_migration("4.0.0", deps=["2.0.0"])
        m5, _ = make_migration("5.0.0", deps=["3.0.0", "4.0.0"])

        for m in [m1, m2, m3, m4, m5]:
            engine.register(m)

        result = engine.apply("5.0.0")
        assert len(result) == 5
        # 1.0.0 must be applied before 2.0.0, etc.
        assert result.index("1.0.0") < result.index("2.0.0")
        assert result.index("2.0.0") < result.index("3.0.0")
        assert result.index("2.0.0") < result.index("4.0.0")


# ===========================================================================
# General / integration tests
# ===========================================================================

class TestGeneralBehaviour:

    def test_register_duplicate_raises(self):
        engine = MigrationEngine()
        m1, _ = make_migration("1.0.0")
        m2, _ = make_migration("1.0.0", desc="duplicate")
        engine.register(m1)
        with pytest.raises(MigrationError):
            engine.register(m2)

    def test_apply_unknown_raises(self):
        engine = MigrationEngine()
        with pytest.raises(MigrationError):
            engine.apply("9.9.9")

    def test_rollback_unapplied_raises(self):
        engine = MigrationEngine()
        m, _ = make_migration("1.0.0")
        engine.register(m)
        with pytest.raises(MigrationError):
            engine.rollback("1.0.0")

    def test_apply_idempotent(self):
        engine = MigrationEngine()
        m, _ = make_migration("1.0.0")
        engine.register(m)
        engine.apply("1.0.0")
        result = engine.apply("1.0.0")
        assert result == []

    def test_execution_log(self):
        engine = MigrationEngine()
        m1, _ = make_migration("1.0.0")
        m2, _ = make_migration("2.0.0")
        engine.register(m1)
        engine.register(m2)
        engine.apply("1.0.0", "2.0.0")
        engine.rollback("2.0.0")
        log = engine.execution_log
        assert "UP: 1.0.0" in log
        assert "UP: 2.0.0" in log
        assert "DOWN: 2.0.0" in log

    def test_invalid_version_format(self):
        with pytest.raises(ValueError):
            SchemaVersion("abc", "bad")
        with pytest.raises(ValueError):
            SchemaVersion("1.2", "bad")

    def test_version_equality(self):
        v1 = SchemaVersion("1.0.0", "a")
        v2 = SchemaVersion("1.0.0", "b")
        assert v1 == v2

    def test_version_history_record_and_remove(self):
        h = VersionHistory()
        v = SchemaVersion("1.0.0", "test")
        h.record(v)
        assert h.count == 1
        assert h.is_applied("1.0.0")
        h.remove(v)
        assert h.count == 0
        assert not h.is_applied("1.0.0")

    def test_dependency_resolution_order(self):
        engine = MigrationEngine()
        m1, _ = make_migration("1.0.0")
        m2, _ = make_migration("2.0.0", deps=["1.0.0"])
        engine.register(m1)
        engine.register(m2)
        result = engine.apply("2.0.0")
        assert result == ["1.0.0", "2.0.0"]
