import pytest
import time
from state_machine import StateMachine, EventLog, replay


class TestStateMachineCore:
    def test_add_state_and_start(self):
        sm = StateMachine()
        sm.add_state("idle")
        sm.add_state("running")
        sm.start("idle")
        assert sm.state == "idle"

    def test_simple_transition(self):
        sm = StateMachine()
        sm.add_state("idle")
        sm.add_state("running")
        sm.add_transition("start", "idle", "running")
        sm.start("idle")
        result = sm.fire("start")
        assert result is True
        assert sm.state == "running"

    def test_invalid_trigger(self):
        sm = StateMachine()
        sm.add_state("idle")
        sm.start("idle")
        result = sm.fire("nonexistent")
        assert result is False
        assert sm.state == "idle"

    def test_wrong_source_state(self):
        sm = StateMachine()
        sm.add_state("idle")
        sm.add_state("running")
        sm.add_state("stopped")
        sm.add_transition("stop", "running", "stopped")
        sm.start("idle")
        result = sm.fire("stop")  # idle -> stopped not defined
        assert result is False
        assert sm.state == "idle"

    def test_multiple_transitions(self):
        sm = StateMachine()
        sm.add_state("idle")
        sm.add_state("running")
        sm.add_state("stopped")
        sm.add_transition("start", "idle", "running")
        sm.add_transition("stop", "running", "stopped")
        sm.add_transition("reset", "stopped", "idle")
        sm.start("idle")
        sm.fire("start")
        assert sm.state == "running"
        sm.fire("stop")
        assert sm.state == "stopped"
        sm.fire("reset")
        assert sm.state == "idle"

    def test_self_transition(self):
        sm = StateMachine()
        sm.add_state("idle")
        sm.add_transition("ping", "idle", "idle")
        sm.start("idle")
        assert sm.fire("ping") is True
        assert sm.state == "idle"


class TestCallbacks:
    def test_on_enter_called(self):
        log = []
        sm = StateMachine()
        sm.add_state("idle", on_enter=lambda: log.append("enter_idle"))
        sm.add_state("running", on_enter=lambda: log.append("enter_running"))
        sm.add_transition("start", "idle", "running")
        sm.start("idle")
        assert "enter_idle" in log
        sm.fire("start")
        assert "enter_running" in log

    def test_on_exit_called(self):
        log = []
        sm = StateMachine()
        sm.add_state("idle", on_exit=lambda: log.append("exit_idle"))
        sm.add_state("running")
        sm.add_transition("start", "idle", "running")
        sm.start("idle")
        sm.fire("start")
        assert "exit_idle" in log

    def test_callback_order(self):
        """转换时应先执行 source.on_exit, 再执行 dest.on_enter"""
        log = []
        sm = StateMachine()
        sm.add_state("a", on_exit=lambda: log.append("exit_a"))
        sm.add_state("b", on_enter=lambda: log.append("enter_b"))
        sm.add_transition("go", "a", "b")
        sm.start("a")
        sm.fire("go")
        assert log.index("exit_a") < log.index("enter_b")

    def test_action_on_transition(self):
        log = []
        sm = StateMachine()
        sm.add_state("idle")
        sm.add_state("running")
        sm.add_transition("start", "idle", "running", action=lambda **kw: log.append(f"action:{kw}"))
        sm.start("idle")
        sm.fire("start", speed=10)
        assert len(log) == 1
        assert "speed" in log[0]


class TestGuard:
    def test_guard_allows(self):
        sm = StateMachine()
        sm.add_state("idle")
        sm.add_state("running")
        sm.add_transition("start", "idle", "running", guard=lambda **kw: True)
        sm.start("idle")
        assert sm.fire("start") is True
        assert sm.state == "running"

    def test_guard_blocks(self):
        sm = StateMachine()
        sm.add_state("idle")
        sm.add_state("running")
        sm.add_transition("start", "idle", "running", guard=lambda **kw: False)
        sm.start("idle")
        assert sm.fire("start") is False
        assert sm.state == "idle"

    def test_guard_receives_kwargs(self):
        received = {}
        def my_guard(**kwargs):
            received.update(kwargs)
            return kwargs.get("authorized", False)

        sm = StateMachine()
        sm.add_state("locked")
        sm.add_state("unlocked")
        sm.add_transition("unlock", "locked", "unlocked", guard=my_guard)
        sm.start("locked")

        assert sm.fire("unlock", authorized=False) is False
        assert sm.state == "locked"

        assert sm.fire("unlock", authorized=True) is True
        assert sm.state == "unlocked"


class TestEventLog:
    def test_log_records_transitions(self):
        sm = StateMachine()
        sm.add_state("idle")
        sm.add_state("running")
        sm.add_state("stopped")
        sm.add_transition("start", "idle", "running")
        sm.add_transition("stop", "running", "stopped")

        log = EventLog()
        log.attach(sm)
        sm.start("idle")
        sm.fire("start")
        sm.fire("stop")

        # 应该有 enter/exit 记录
        types = [e["type"] for e in log.entries]
        assert "enter" in types
        assert "exit" in types

    def test_log_has_state_info(self):
        sm = StateMachine()
        sm.add_state("a")
        sm.add_state("b")
        sm.add_transition("go", "a", "b")

        log = EventLog()
        log.attach(sm)
        sm.start("a")
        sm.fire("go")

        # 每条记录应有 state 字段
        for entry in log.entries:
            assert "state" in entry
            assert "type" in entry

    def test_log_records_trigger(self):
        sm = StateMachine()
        sm.add_state("a")
        sm.add_state("b")
        sm.add_transition("go", "a", "b")

        log = EventLog()
        log.attach(sm)
        sm.start("a")
        sm.fire("go")

        trigger_entries = [e for e in log.entries if e.get("trigger")]
        assert len(trigger_entries) > 0
        assert any(e["trigger"] == "go" for e in trigger_entries)

    def test_log_has_timestamp(self):
        sm = StateMachine()
        sm.add_state("a")
        sm.add_state("b")
        sm.add_transition("go", "a", "b")

        log = EventLog()
        log.attach(sm)
        sm.start("a")
        sm.fire("go")

        for entry in log.entries:
            assert "timestamp" in entry
            assert isinstance(entry["timestamp"], float)

    def test_log_clear(self):
        sm = StateMachine()
        sm.add_state("a")
        sm.add_state("b")
        sm.add_transition("go", "a", "b")

        log = EventLog()
        log.attach(sm)
        sm.start("a")
        sm.fire("go")
        assert len(log.entries) > 0
        log.clear()
        assert len(log.entries) == 0


class TestReplay:
    def test_replay_reaches_same_state(self):
        """回放 log 应该让新 machine 到达相同最终状态"""
        sm1 = StateMachine()
        sm1.add_state("idle")
        sm1.add_state("running")
        sm1.add_state("stopped")
        sm1.add_transition("start", "idle", "running")
        sm1.add_transition("stop", "running", "stopped")

        log = EventLog()
        log.attach(sm1)
        sm1.start("idle")
        sm1.fire("start")
        sm1.fire("stop")
        assert sm1.state == "stopped"

        # 新 machine 通过 replay 到达相同状态
        sm2 = StateMachine()
        sm2.add_state("idle")
        sm2.add_state("running")
        sm2.add_state("stopped")
        sm2.add_transition("start", "idle", "running")
        sm2.add_transition("stop", "running", "stopped")
        sm2.start("idle")

        final = replay(log.entries, sm2)
        assert final == "stopped"
        assert sm2.state == "stopped"

    def test_replay_with_guards(self):
        """回放时 guard 仍然生效"""
        sm1 = StateMachine()
        sm1.add_state("idle")
        sm1.add_state("active")
        sm1.add_transition("go", "idle", "active", guard=lambda **kw: kw.get("ok", False))

        log = EventLog()
        log.attach(sm1)
        sm1.start("idle")
        sm1.fire("go", ok=False)  # blocked
        sm1.fire("go", ok=True)   # allowed
        assert sm1.state == "active"

        sm2 = StateMachine()
        sm2.add_state("idle")
        sm2.add_state("active")
        sm2.add_transition("go", "idle", "active", guard=lambda **kw: kw.get("ok", False))
        sm2.start("idle")

        final = replay(log.entries, sm2)
        assert final == "active"

    def test_replay_empty_log(self):
        sm = StateMachine()
        sm.add_state("idle")
        sm.start("idle")

        final = replay([], sm)
        assert final == "idle"


class TestIntegration:
    def test_traffic_light(self):
        """模拟交通灯状态机"""
        sm = StateMachine()
        sm.add_state("red")
        sm.add_state("green")
        sm.add_state("yellow")
        sm.add_transition("next", "red", "green")
        sm.add_transition("next", "green", "yellow")
        sm.add_transition("next", "yellow", "red")
        sm.start("red")

        log = EventLog()
        log.attach(sm)

        states = [sm.state]
        for _ in range(6):
            sm.fire("next")
            states.append(sm.state)

        assert states == ["red", "green", "yellow", "red", "green", "yellow", "red"]

    def test_door_with_guard(self):
        """门锁状态机: locked -> unlocked 需要密码"""
        sm = StateMachine()
        sm.add_state("locked")
        sm.add_state("unlocked")
        sm.add_state("open")
        sm.add_transition("unlock", "locked", "unlocked",
                          guard=lambda **kw: kw.get("password") == "secret")
        sm.add_transition("open", "unlocked", "open")
        sm.add_transition("close", "open", "unlocked")
        sm.add_transition("lock", "unlocked", "locked")
        sm.start("locked")

        assert sm.fire("unlock", password="wrong") is False
        assert sm.state == "locked"

        assert sm.fire("unlock", password="secret") is True
        assert sm.state == "unlocked"

        sm.fire("open")
        assert sm.state == "open"

        sm.fire("close")
        sm.fire("lock")
        assert sm.state == "locked"
