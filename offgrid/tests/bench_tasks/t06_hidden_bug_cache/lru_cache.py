# LRU 缓存实现 — 支持 TTL 过期、最大容量、统计信息
# 有用户报告缓存行为不符合预期，请找出并修复所有 bug

import time


class LRUCache:
    def __init__(self, capacity: int, default_ttl: float = 0):
        """
        capacity: 最大缓存条目数
        default_ttl: 默认过期时间(秒)，0 表示永不过期
        """
        self.capacity = capacity
        self.default_ttl = default_ttl
        self._cache = {}  # key -> value
        self._timestamps = {}  # key -> insert_time
        self._ttls = {}  # key -> ttl
        self._access_order = []  # 最近访问的 key 列表，尾部是最近的
        self._hits = 0
        self._misses = 0

    def get(self, key, default=None):
        """获取缓存值。如果过期则删除并返回 default。"""
        if key not in self._cache:
            self._misses += 1
            return default

        # 检查 TTL
        ttl = self._ttls.get(key, self.default_ttl)
        if ttl > 0:
            elapsed = time.time() - self._timestamps[key]
            if elapsed > ttl:
                self.delete(key)
                self._misses += 1
                return default

        self._hits += 1
        # 更新访问顺序
        self._access_order.remove(key)
        self._access_order.append(key)
        return self._cache[key]

    def put(self, key, value, ttl=None):
        """写入缓存。ttl=None 使用 default_ttl。"""
        if ttl is None:
            ttl = self.default_ttl

        # 如果 key 已存在，更新
        if key in self._cache:
            self._cache[key] = value
            self._timestamps[key] = time.time()
            self._ttls[key] = ttl
            self._access_order.remove(key)
            self._access_order.append(key)
            return

        # 容量满了，淘汰最久未使用的
        while len(self._cache) >= self.capacity:
            self._evict()

        self._cache[key] = value
        self._timestamps[key] = time.time()
        self._ttls[key] = ttl
        self._access_order.append(key)

    def delete(self, key):
        """删除缓存条目"""
        if key in self._cache:
            del self._cache[key]
            del self._timestamps[key]
            del self._ttls[key]

    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._timestamps.clear()
        self._ttls.clear()
        self._access_order.clear()

    def size(self) -> int:
        return len(self._cache)

    def stats(self) -> dict:
        """返回缓存统计"""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "size": self.size(),
            "capacity": self.capacity,
        }

    def keys(self) -> list:
        """返回所有未过期的 key（按 LRU 顺序，最近使用的在后）"""
        return list(self._access_order)

    def _evict(self):
        """淘汰最久未使用的条目"""
        if not self._access_order:
            return
        oldest_key = self._access_order.pop(0)
        del self._cache[oldest_key]
        del self._timestamps[oldest_key]
        del self._ttls[oldest_key]
