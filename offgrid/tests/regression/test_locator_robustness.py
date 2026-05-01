"""Regression tests for Locator JSON parsing robustness."""

import pytest

from offgrid.experts.locator import LocatorExpert


# ── Group 1: Valid variants that must parse successfully ──────────────

VALID_FILE_LIST_CASES = [
    pytest.param(
        '{"relevant_files": ["app.py"]}',
        ["app.py"],
        id="standard_json",
    ),
    pytest.param(
        '```json\n{"relevant_files": ["app.py"]}\n```',
        ["app.py"],
        id="markdown_code_block",
    ),
    pytest.param(
        '我分析了代码：\n{"relevant_files": ["app.py"]}',
        ["app.py"],
        id="text_before_json",
    ),
    pytest.param(
        '{"relevant_files": ["app.py"]}\n以上是分析。',
        ["app.py"],
        id="text_after_json",
    ),
    pytest.param(
        '  {  "relevant_files":  ["app.py"]  }  ',
        ["app.py"],
        id="extra_whitespace",
    ),
    pytest.param(
        '{"relevant_files": ["app.py", "config.py", "utils.py"]}',
        ["app.py", "config.py", "utils.py"],
        id="multiple_files",
    ),
    pytest.param(
        '{"relevant_files": ["src/auth/login.py"]}',
        ["src/auth/login.py"],
        id="path_files",
    ),
    pytest.param(
        '<think>分析中...</think>\n{"relevant_files": ["app.py"]}',
        ["app.py"],
        id="thinking_tags",
    ),
]


@pytest.mark.parametrize("raw, expected", VALID_FILE_LIST_CASES)
def test_parse_file_list_valid(raw: str, expected: list[str]):
    result = LocatorExpert._parse_file_list(raw)
    assert result == expected


# ── Group 2: Truncated / broken JSON — no crash, returns list ─────────

BROKEN_JSON_CASES = [
    pytest.param(
        '```json\n{"relevant_files": ["app.py", "config.py"\n```',
        id="unclosed_bracket",
    ),
    pytest.param(
        '{"relevant_files": ["app.py"',
        id="no_closing_brace",
    ),
    pytest.param(
        '["app.py", "config.py"]',
        id="bare_list_no_key",
    ),
    pytest.param(
        '{"relevant_files": ["app.py", "con',
        id="truncated_mid_word",
    ),
]


@pytest.mark.parametrize("raw", BROKEN_JSON_CASES)
def test_parse_file_list_broken_no_crash(raw: str):
    result = LocatorExpert._parse_file_list(raw)
    assert isinstance(result, list)


# ── Group 3: Completely invalid output — empty list, no exception ─────

INVALID_OUTPUT_CASES = [
    pytest.param("我无法理解这个任务", id="chinese_refusal"),
    pytest.param("", id="empty_string"),
    pytest.param("   ", id="whitespace_only"),
    pytest.param("null", id="null_literal"),
    pytest.param("false", id="false_literal"),
]


@pytest.mark.parametrize("raw", INVALID_OUTPUT_CASES)
def test_parse_file_list_invalid_returns_empty(raw: str):
    result = LocatorExpert._parse_file_list(raw)
    assert result == []


# ── Group 4: _parse_func_result ───────────────────────────────────────

def test_parse_func_result_valid():
    raw = '{"relevant_functions": ["add", "subtract"], "edit_locations": ["calc.py:add"]}'
    funcs, locs = LocatorExpert._parse_func_result(raw)
    assert funcs == ["add", "subtract"]
    assert locs == ["calc.py:add"]


def test_parse_func_result_invalid():
    funcs, locs = LocatorExpert._parse_func_result("garbage text")
    assert funcs == []
    assert locs == []


# ── Group 5: tmp path prefixes preserved ──────────────────────────────

def test_tmp_path_prefix_preserved():
    raw = '{"relevant_files": ["tmp_abc123/project/src/app.py"]}'
    result = LocatorExpert._parse_file_list(raw)
    assert result == ["tmp_abc123/project/src/app.py"]
