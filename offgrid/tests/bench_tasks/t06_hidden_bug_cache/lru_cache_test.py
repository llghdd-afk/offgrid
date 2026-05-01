import pytest
import time
from lru_cache import LRUCache


class TestBasicOperations:
    def test_put_and_get(self):
        cache = LRUCache(capacity=3)
        cache.put("a", 1)
        assert cache.get("a") == 1

    def test_get_missing(self):
        cache = LRUCache(capacity=3)
        assert cache.get("missing") is None
        assert cache.get("missing", default="fallback") == "fallback"

    def test_update_existing(self):
        cache = LRUCache(capacity=3)
        cache.put("a", 1)
        cache.put("a", 2)
        assert cache.get("a") == 2
        assert cache.size() == 1

    def test_delete(self):
        cache = LRUCache(capacity=3)
        cache.put("a", 1)
        cache.delete("a")
        assert cache.get("a") is None
        assert cache.size() == 0

    def test_delete_nonexistent(self):
        cache = LRUCache(capacity=3)
        cache.delete("nope")  # should not raise

    def test_clear(self):
        cache = LRUCache(capacity=3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.clear()
        assert cache.size() == 0
        assert cache.get("a") is None


class TestLRUEviction:
    def test_evicts_oldest(self):
        cache = LRUCache(capacity=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)  # should evict "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_access_refreshes_order(self):
        cache = LRUCache(capacity=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")  # refresh "a"
        cache.put("c", 3)  # should evict "b" (least recently used)
        assert cache.get("a") == 1
        assert cache.get("b") is None
        assert cache.get("c") == 3

    def test_update_refreshes_order(self):
        cache = LRUCache(capacity=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("a", 10)  # update "a", refreshes it
        cache.put("c", 3)  # should evict "b"
        assert cache.get("a") == 10
        assert cache.get("b") is None

    def test_delete_then_add(self):
        """删除后再添加和驱逐应正常工作"""
        cache = LRUCache(capacity=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.delete("a")
        cache.put("c", 3)
        cache.put("d", 4)  # should evict "b" or "c", not crash
        assert cache.size() == 2
        assert cache.get("a") is None

    def test_delete_and_eviction_interaction(self):
        """删除后再填满，eviction 不应引用已删除的 key"""
        cache = LRUCache(capacity=3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        cache.delete("b")
        cache.put("d", 4)
        cache.put("e", 5)  # capacity=3, should evict oldest remaining
        assert cache.size() <= 3
        # "b" 已删除，不应影响 eviction
        assert cache.get("b") is None


class TestTTL:
    def test_ttl_expiry(self):
        cache = LRUCache(capacity=10, default_ttl=0.1)
        cache.put("a", 1)
        assert cache.get("a") == 1
        time.sleep(0.15)
        assert cache.get("a") is None

    def test_per_key_ttl(self):
        cache = LRUCache(capacity=10)
        cache.put("short", 1, ttl=0.1)
        cache.put("long", 2, ttl=10.0)
        time.sleep(0.15)
        assert cache.get("short") is None
        assert cache.get("long") == 2

    def test_no_ttl_never_expires(self):
        cache = LRUCache(capacity=10, default_ttl=0)
        cache.put("a", 1)
        # default_ttl=0 means no expiry
        assert cache.get("a") == 1

    def test_keys_excludes_expired(self):
        """keys() 应该只返回未过期的 key"""
        cache = LRUCache(capacity=10, default_ttl=0.1)
        cache.put("a", 1)
        cache.put("b", 2, ttl=10.0)
        time.sleep(0.15)
        keys = cache.keys()
        assert "a" not in keys
        assert "b" in keys


class TestStats:
    def test_hit_miss_tracking(self):
        cache = LRUCache(capacity=3)
        cache.put("a", 1)
        cache.get("a")  # hit
        cache.get("b")  # miss
        cache.get("c")  # miss
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 2
        assert abs(stats["hit_rate"] - 1/3) < 0.01

    def test_expired_counts_as_miss(self):
        cache = LRUCache(capacity=10, default_ttl=0.1)
        cache.put("a", 1)
        cache.get("a")  # hit
        time.sleep(0.15)
        cache.get("a")  # miss (expired)
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_stats_size(self):
        cache = LRUCache(capacity=5)
        cache.put("a", 1)
        cache.put("b", 2)
        assert cache.stats()["size"] == 2
        assert cache.stats()["capacity"] == 5


class TestEdgeCases:
    def test_capacity_one(self):
        cache = LRUCache(capacity=1)
        cache.put("a", 1)
        cache.put("b", 2)
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.size() == 1

    def test_overwrite_does_not_increase_size(self):
        cache = LRUCache(capacity=2)
        cache.put("a", 1)
        cache.put("a", 2)
        cache.put("a", 3)
        assert cache.size() == 1

    def test_many_operations(self):
        cache = LRUCache(capacity=3)
        for i in range(100):
            cache.put(f"key{i}", i)
        assert cache.size() == 3
        # 最后3个应该在缓存中
        assert cache.get("key99") == 99
        assert cache.get("key98") == 98
        assert cache.get("key97") == 97
