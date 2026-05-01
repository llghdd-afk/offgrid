import pytest
import time
from event_bus import EventBus


# ── 基础订阅/发布 ──

class TestBasicPubSub:
    def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []
        bus.subscribe("test", lambda e: received.append(e["data"]))
        bus.publish("test", data="hello")
        assert received == ["hello"]

    def test_multiple_handlers(self):
        bus = EventBus()
        log = []
        bus.subscribe("evt", lambda e: log.append("a"))
        bus.subscribe("evt", lambda e: log.append("b"))
        bus.publish("evt")
        assert len(log) == 2

    def test_unsubscribe(self):
        bus = EventBus()
        log = []
        handler = lambda e: log.append(1)
        bus.subscribe("evt", handler)
        bus.unsubscribe("evt", handler)
        bus.publish("evt")
        assert log == []

    def test_no_handlers(self):
        bus = EventBus()
        event = bus.publish("nobody_listens", data="test")
        assert event is not None
        assert event["results"] == []


# ── 优先级 ──

class TestPriority:
    def test_priority_order(self):
        """高优先级的 handler 应该先执行"""
        bus = EventBus()
        order = []
        bus.subscribe("evt", lambda e: order.append("low"), priority=1)
        bus.subscribe("evt", lambda e: order.append("high"), priority=10)
        bus.subscribe("evt", lambda e: order.append("mid"), priority=5)
        bus.publish("evt")
        assert order == ["high", "mid", "low"]

    def test_same_priority_all_execute(self):
        bus = EventBus()
        count = []
        bus.subscribe("evt", lambda e: count.append(1), priority=0)
        bus.subscribe("evt", lambda e: count.append(2), priority=0)
        bus.publish("evt")
        assert len(count) == 2


# ── 通配符匹配 ──

class TestWildcard:
    def test_exact_match(self):
        bus = EventBus()
        log = []
        bus.subscribe("user.login", lambda e: log.append(1))
        bus.publish("user.login")
        assert len(log) == 1

    def test_star_wildcard(self):
        bus = EventBus()
        log = []
        bus.subscribe("user.*", lambda e: log.append(e["name"]))
        bus.publish("user.login")
        bus.publish("user.logout")
        bus.publish("order.created")  # should NOT match
        assert log == ["user.login", "user.logout"]

    def test_star_only_one_level(self):
        """user.* 应该匹配 user.login 但不匹配 user.login.failed"""
        bus = EventBus()
        log = []
        bus.subscribe("user.*", lambda e: log.append(e["name"]))
        bus.publish("user.login")
        bus.publish("user.login.failed")
        assert log == ["user.login"]

    def test_prefix_wildcard(self):
        bus = EventBus()
        log = []
        bus.subscribe("*.error", lambda e: log.append(e["name"]))
        bus.publish("db.error")
        bus.publish("api.error")
        bus.publish("api.success")  # should NOT match
        assert len(log) == 2


# ── 异常处理 ──

class TestErrorHandling:
    def test_handler_error_continues(self):
        """一个 handler 抛异常不应阻止其他 handler 执行"""
        bus = EventBus()
        results = []

        def bad_handler(e):
            raise ValueError("boom")

        def good_handler(e):
            results.append("ok")
            return "ok"

        bus.subscribe("evt", bad_handler, priority=10)
        bus.subscribe("evt", good_handler, priority=1)
        event = bus.publish("evt")

        # good_handler 应该也执行了
        assert "ok" in results
        # 错误应被捕获在 results 里
        assert any("error" in str(r) for r in event["results"])

    def test_error_captured_in_results(self):
        bus = EventBus()

        def fail(e):
            raise RuntimeError("fail!")

        bus.subscribe("evt", fail)
        event = bus.publish("evt")
        assert len(event["results"]) == 1
        assert "error" in event["results"][0]


# ── 中间件 ──

class TestMiddleware:
    def test_middleware_modifies_event(self):
        bus = EventBus()
        received = []

        def add_meta(event):
            event["meta"] = "added"
            return event

        bus.add_middleware(add_meta)
        bus.subscribe("evt", lambda e: received.append(e.get("meta")))
        bus.publish("evt")
        assert received == ["added"]

    def test_middleware_cancels_event(self):
        bus = EventBus()
        log = []

        def block_all(event):
            event["cancelled"] = True
            return event

        bus.add_middleware(block_all)
        bus.subscribe("evt", lambda e: log.append(1))
        event = bus.publish("evt")
        assert log == []
        assert event["cancelled"] is True

    def test_middleware_chain_order(self):
        bus = EventBus()
        order = []

        def mw1(event):
            order.append("mw1")
            return event

        def mw2(event):
            order.append("mw2")
            return event

        bus.add_middleware(mw1)
        bus.add_middleware(mw2)
        bus.subscribe("evt", lambda e: None)
        bus.publish("evt")
        assert order == ["mw1", "mw2"]


# ── 历史和回放 ──

class TestHistory:
    def test_history_recorded(self):
        bus = EventBus()
        bus.subscribe("evt", lambda e: None)
        bus.publish("evt", data="d1")
        bus.publish("evt", data="d2")
        history = bus.get_history()
        assert len(history) == 2

    def test_history_filter_by_name(self):
        bus = EventBus()
        bus.publish("a", data=1)
        bus.publish("b", data=2)
        bus.publish("a", data=3)
        assert len(bus.get_history("a")) == 2
        assert len(bus.get_history("b")) == 1

    def test_history_limit(self):
        bus = EventBus()
        for i in range(10):
            bus.publish("evt", data=i)
        assert len(bus.get_history(limit=3)) == 3

    def test_clear_history(self):
        bus = EventBus()
        bus.publish("evt")
        bus.clear_history()
        assert len(bus.get_history()) == 0


class TestReplay:
    def test_replay_reruns_events(self):
        bus = EventBus()
        log = []
        bus.subscribe("evt", lambda e: log.append(e["data"]))
        bus.publish("evt", data="first")
        assert len(log) == 1

        bus.replay()
        # replay 应该重新触发，log 里应该有新增
        assert len(log) >= 2

    def test_replay_new_timestamp(self):
        """回放的事件应该有新的 timestamp"""
        bus = EventBus()
        bus.subscribe("evt", lambda e: None)
        bus.publish("evt", data="test")
        old_ts = bus.get_history()[0]["timestamp"]

        time.sleep(0.05)
        bus.replay()
        new_history = bus.get_history()
        # 最后一条应该是回放的，timestamp 应该更新
        assert new_history[-1]["timestamp"] > old_ts


# ── handler_count ──

class TestHandlerCount:
    def test_count_specific(self):
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        assert bus.handler_count("a") == 2
        assert bus.handler_count("b") == 1

    def test_count_all(self):
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        assert bus.handler_count() == 2


# ── 重构验证 ──

class TestRefactoring:
    def test_event_store_class_exists(self):
        """重构后应该有 EventStore 类"""
        from event_bus import EventStore
        store = EventStore()
        assert hasattr(store, 'add')
        assert hasattr(store, 'get_all')
        assert hasattr(store, 'get_by_name')
        assert hasattr(store, 'clear')

    def test_event_replay_class_exists(self):
        """重构后应该有 EventReplay 类"""
        from event_bus import EventReplay
        assert hasattr(EventReplay, 'replay')

    def test_event_bus_uses_store(self):
        """EventBus 应该使用 EventStore 来存储历史"""
        from event_bus import EventStore
        bus = EventBus()
        assert hasattr(bus, '_store') or hasattr(bus, 'store')

    def test_event_bus_not_monolithic(self):
        """event_bus.py 中的 EventBus 类不应超过 80 行"""
        import inspect
        from event_bus import EventBus
        source = inspect.getsource(EventBus)
        lines = [l for l in source.split('\n') if l.strip()]
        assert len(lines) <= 80, f"EventBus should be <=80 lines after refactoring, got {len(lines)}"
