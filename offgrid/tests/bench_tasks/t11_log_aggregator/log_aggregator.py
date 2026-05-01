"""
Log Aggregator — 日志过滤与聚合工具

支持按时间范围、日志级别过滤，以及按时间窗口聚合统计。
"""

from datetime import datetime, timedelta
from collections import defaultdict


class LogEntry:
    """单条日志记录"""

    def __init__(self, timestamp: str, level: str, message: str, source: str = "app"):
        self.timestamp = datetime.fromisoformat(timestamp)
        self.level = level.upper()
        self.message = message
        self.source = source

    def __repr__(self):
        return f"LogEntry({self.timestamp.isoformat()}, {self.level}, {self.message!r})"


class LogAggregator:
    """日志聚合器：支持过滤和聚合"""

    LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def __init__(self):
        self.entries = []

    def add(self, entry: LogEntry):
        self.entries.append(entry)

    def add_many(self, entries: list):
        self.entries.extend(entries)

    def filter_by_time(self, start: str, end: str) -> list:
        """按时间范围过滤（包含 start 和 end 边界）"""
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        # BUG 1: off-by-one — 用 < 而不是 <= 来比较 end，
        # 导致恰好在 end 时间点的日志被排除
        return [e for e in self.entries if start_dt <= e.timestamp < end_dt]

    def filter_by_level(self, min_level: str) -> list:
        """按最低级别过滤（返回 >= min_level 的所有日志）"""
        # BUG 2: 直接用字符串比较而不是级别索引比较，
        # 导致 "WARNING" > "ERROR" (字母序 W > E)
        return [e for e in self.entries if e.level >= min_level.upper()]

    def filter_by_source(self, source: str) -> list:
        """按来源过滤"""
        return [e for e in self.entries if e.source == source]

    def aggregate_by_level(self, entries: list = None) -> dict:
        """按级别统计数量"""
        if entries is None:
            entries = self.entries
        result = defaultdict(int)
        for e in entries:
            result[e.level] += 1
        return dict(result)

    def aggregate_by_window(self, window_minutes: int, entries: list = None) -> list:
        """按时间窗口聚合，返回每个窗口的统计"""
        if entries is None:
            entries = self.entries
        if not entries:
            return []

        sorted_entries = sorted(entries, key=lambda e: e.timestamp)
        window = timedelta(minutes=window_minutes)

        windows = []
        current_start = sorted_entries[0].timestamp
        current_entries = []

        for entry in sorted_entries:
            if entry.timestamp - current_start >= window:
                # 保存当前窗口
                windows.append({
                    "start": current_start.isoformat(),
                    "end": (current_start + window).isoformat(),
                    "count": len(current_entries),
                    "levels": self.aggregate_by_level(current_entries),
                })
                current_start = entry.timestamp
                current_entries = [entry]
            else:
                current_entries.append(entry)

        # 最后一个窗口
        if current_entries:
            windows.append({
                "start": current_start.isoformat(),
                "end": (current_start + window).isoformat(),
                "count": len(current_entries),
                "levels": self.aggregate_by_level(current_entries),
            })

        return windows

    def search(self, keyword: str, entries: list = None) -> list:
        """按关键词搜索日志消息"""
        if entries is None:
            entries = self.entries
        return [e for e in entries if keyword.lower() in e.message.lower()]

    def chain_filter(self, filters: list) -> list:
        """链式过滤：依次应用多个过滤条件"""
        result = self.entries[:]
        for f in filters:
            ftype = f["type"]
            if ftype == "time":
                agg = LogAggregator()
                agg.entries = result
                result = agg.filter_by_time(f["start"], f["end"])
            elif ftype == "level":
                agg = LogAggregator()
                agg.entries = result
                result = agg.filter_by_level(f["min_level"])
            elif ftype == "source":
                result = [e for e in result if e.source == f["source"]]
            elif ftype == "search":
                result = [e for e in result if f["keyword"].lower() in e.message.lower()]
        return result
