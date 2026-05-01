"""Tests for LogAggregator"""

import pytest
from log_aggregator import LogEntry, LogAggregator


@pytest.fixture
def sample_logs():
    """创建测试用的日志数据"""
    return [
        LogEntry("2024-01-15T10:00:00", "DEBUG", "Starting application", "app"),
        LogEntry("2024-01-15T10:05:00", "INFO", "User login successful", "auth"),
        LogEntry("2024-01-15T10:10:00", "WARNING", "High memory usage detected", "monitor"),
        LogEntry("2024-01-15T10:15:00", "ERROR", "Database connection failed", "db"),
        LogEntry("2024-01-15T10:20:00", "INFO", "Retry database connection", "db"),
        LogEntry("2024-01-15T10:25:00", "ERROR", "Connection timeout", "network"),
        LogEntry("2024-01-15T10:30:00", "CRITICAL", "System shutdown initiated", "app"),
        LogEntry("2024-01-15T10:35:00", "INFO", "Backup completed", "backup"),
        LogEntry("2024-01-15T10:40:00", "DEBUG", "Cache cleared", "cache"),
        LogEntry("2024-01-15T10:45:00", "WARNING", "Disk space low", "monitor"),
    ]


@pytest.fixture
def aggregator(sample_logs):
    agg = LogAggregator()
    agg.add_many(sample_logs)
    return agg


class TestFilterByTime:
    def test_basic_range(self, aggregator):
        """过滤 10:05 到 10:25 之间的日志"""
        result = aggregator.filter_by_time("2024-01-15T10:05:00", "2024-01-15T10:25:00")
        assert len(result) == 4  # 10:05, 10:10, 10:15, 10:20 — 包含两端

    def test_exact_boundary_included(self, aggregator):
        """确认边界时间点被包含"""
        result = aggregator.filter_by_time("2024-01-15T10:00:00", "2024-01-15T10:00:00")
        assert len(result) == 1  # 恰好 10:00 的日志应该被包含

    def test_end_boundary_included(self, aggregator):
        """end 时间点的日志也应该被包含"""
        result = aggregator.filter_by_time("2024-01-15T10:25:00", "2024-01-15T10:30:00")
        assert len(result) == 2  # 10:25 和 10:30 都应该被包含

    def test_empty_range(self, aggregator):
        """没有日志在范围内"""
        result = aggregator.filter_by_time("2024-01-15T11:00:00", "2024-01-15T12:00:00")
        assert len(result) == 0

    def test_full_range(self, aggregator):
        """包含所有日志的范围"""
        result = aggregator.filter_by_time("2024-01-15T09:00:00", "2024-01-15T11:00:00")
        assert len(result) == 10


class TestFilterByLevel:
    def test_filter_error_and_above(self, aggregator):
        """ERROR 及以上应该返回 ERROR + CRITICAL"""
        result = aggregator.filter_by_level("ERROR")
        levels = {e.level for e in result}
        assert levels == {"ERROR", "CRITICAL"}
        assert len(result) == 3  # 2 ERROR + 1 CRITICAL

    def test_filter_warning_and_above(self, aggregator):
        """WARNING 及以上"""
        result = aggregator.filter_by_level("WARNING")
        levels = {e.level for e in result}
        assert levels == {"WARNING", "ERROR", "CRITICAL"}
        assert len(result) == 5  # 2 WARNING + 2 ERROR + 1 CRITICAL

    def test_filter_debug_returns_all(self, aggregator):
        """DEBUG 是最低级别，应该返回所有日志"""
        result = aggregator.filter_by_level("DEBUG")
        assert len(result) == 10

    def test_filter_critical_only(self, aggregator):
        """只返回 CRITICAL"""
        result = aggregator.filter_by_level("CRITICAL")
        assert len(result) == 1
        assert result[0].level == "CRITICAL"

    def test_filter_case_insensitive(self, aggregator):
        """级别过滤应不区分大小写"""
        result = aggregator.filter_by_level("error")
        assert len(result) == 3

    def test_filter_info_and_above(self, aggregator):
        """INFO 及以上，排除 DEBUG"""
        result = aggregator.filter_by_level("INFO")
        levels = {e.level for e in result}
        assert "DEBUG" not in levels
        assert len(result) == 8  # 所有非 DEBUG 的


class TestAggregateByLevel:
    def test_all_entries(self, aggregator):
        result = aggregator.aggregate_by_level()
        assert result["DEBUG"] == 2
        assert result["INFO"] == 3
        assert result["WARNING"] == 2
        assert result["ERROR"] == 2
        assert result["CRITICAL"] == 1

    def test_filtered_entries(self, aggregator):
        errors = aggregator.filter_by_level("ERROR")
        result = aggregator.aggregate_by_level(errors)
        assert result.get("ERROR", 0) == 2
        assert result.get("CRITICAL", 0) == 1
        assert "DEBUG" not in result
        assert "INFO" not in result


class TestAggregateByWindow:
    def test_15_minute_windows(self, aggregator):
        windows = aggregator.aggregate_by_window(15)
        assert len(windows) >= 3  # 45 分钟范围，15 分钟窗口

    def test_window_counts_add_up(self, aggregator):
        windows = aggregator.aggregate_by_window(60)
        total = sum(w["count"] for w in windows)
        assert total == 10

    def test_empty_entries(self, aggregator):
        assert aggregator.aggregate_by_window(10, entries=[]) == []


class TestSearch:
    def test_keyword_found(self, aggregator):
        result = aggregator.search("database")
        assert len(result) == 2

    def test_case_insensitive(self, aggregator):
        result = aggregator.search("DATABASE")
        assert len(result) == 2

    def test_keyword_not_found(self, aggregator):
        result = aggregator.search("nonexistent")
        assert len(result) == 0


class TestChainFilter:
    def test_time_then_level(self, aggregator):
        """先按时间过滤再按级别过滤"""
        result = aggregator.chain_filter([
            {"type": "time", "start": "2024-01-15T10:00:00", "end": "2024-01-15T10:30:00"},
            {"type": "level", "min_level": "ERROR"},
        ])
        # 10:00-10:30 包含 7 条日志，其中 ERROR 及以上有 3 条 (2 ERROR + 1 CRITICAL)
        assert len(result) == 3

    def test_source_then_search(self, aggregator):
        """先按来源再按关键词"""
        result = aggregator.chain_filter([
            {"type": "source", "source": "db"},
            {"type": "search", "keyword": "connection"},
        ])
        assert len(result) == 1  # 只有 "Database connection failed"

    def test_empty_chain(self, aggregator):
        """空过滤链返回所有日志"""
        result = aggregator.chain_filter([])
        assert len(result) == 10


class TestFilterBySource:
    def test_filter_db(self, aggregator):
        result = aggregator.filter_by_source("db")
        assert len(result) == 2

    def test_filter_nonexistent(self, aggregator):
        result = aggregator.filter_by_source("nonexistent")
        assert len(result) == 0
