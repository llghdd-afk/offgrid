"""E2E task definitions — Group 1: Code fix + generation (SWE core scenarios)."""

import os


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _write(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# T1  Fix off-by-one in fibonacci
# ---------------------------------------------------------------------------

_T1_FIBONACCI_BUGGY = """\
def fibonacci(n):
    if n <= 0:
        return 0
    if n == 1:
        return 1
    a, b = 0, 1
    for _ in range(n):  # BUG: should be range(n - 1)
        a, b = b, a + b
    return b
"""

_T1_TEST = """\
from src.math_utils import fibonacci

def test_fibonacci_6():
    assert fibonacci(6) == 8
"""


def _t1_setup(project_root: str):
    _write(os.path.join(project_root, "src", "math_utils.py"), _T1_FIBONACCI_BUGGY)
    _write(os.path.join(project_root, "tests", "test_math.py"), _T1_TEST)


def _t1_check(project_root: str, result: dict) -> tuple:
    path = os.path.join(project_root, "src", "math_utils.py")
    if not os.path.exists(path):
        return False, "src/math_utils.py not found"
    content = _read(path)
    if content.strip() == _T1_FIBONACCI_BUGGY.strip():
        return False, "File was not modified"
    return True, "fibonacci bug fix detected"


# ---------------------------------------------------------------------------
# T2  Fix variable typo
# ---------------------------------------------------------------------------

_T2_BILLING_BUGGY = """\
def calculate_total(items):
    totla = 0
    for item in items:
        totla += item.get("price", 0) * item.get("quantity", 1)
    return totla
"""


def _t2_setup(project_root: str):
    _write(os.path.join(project_root, "src", "billing.py"), _T2_BILLING_BUGGY)


def _t2_check(project_root: str, result: dict) -> tuple:
    path = os.path.join(project_root, "src", "billing.py")
    if not os.path.exists(path):
        return False, "src/billing.py not found"
    content = _read(path)
    if "totla" in content:
        return False, "Typo 'totla' still present"
    if "total" not in content:
        return False, "'total' not found in file"
    return True, "Variable typo fixed"


# ---------------------------------------------------------------------------
# T3  Add function to existing file
# ---------------------------------------------------------------------------

_T3_STRING_UTILS = """\
def capitalize_first(s):
    return s[0].upper() + s[1:]
"""


def _t3_setup(project_root: str):
    _write(os.path.join(project_root, "src", "string_utils.py"), _T3_STRING_UTILS)


def _t3_check(project_root: str, result: dict) -> tuple:
    path = os.path.join(project_root, "src", "string_utils.py")
    if not os.path.exists(path):
        return False, "src/string_utils.py not found"
    content = _read(path)
    if "def reverse_string" not in content:
        return False, "'def reverse_string' not found"
    return True, "reverse_string function added"


# ---------------------------------------------------------------------------
# T4  Fix logic bug in is_palindrome
# ---------------------------------------------------------------------------

_T4_CHECKER_BUGGY = """\
def is_palindrome(s):
    if not s:
        return False
    return s == s[::-1]
"""


def _t4_setup(project_root: str):
    _write(os.path.join(project_root, "src", "checker.py"), _T4_CHECKER_BUGGY)


def _t4_check(project_root: str, result: dict) -> tuple:
    path = os.path.join(project_root, "src", "checker.py")
    if not os.path.exists(path):
        return False, "src/checker.py not found"
    content = _read(path)
    if "if not s:\n        return False" in content:
        return False, "Bug still present: empty string returns False"
    if "if not s:" in content and "return False" in content:
        return False, "Bug still present: empty string returns False"
    return True, "is_palindrome empty-string bug fixed"


# ---------------------------------------------------------------------------
# T5  Generate new calculator.py
# ---------------------------------------------------------------------------

def _t5_setup(project_root: str):
    os.makedirs(project_root, exist_ok=True)


def _t5_check(project_root: str, result: dict) -> tuple:
    # Search common locations
    candidates = [
        os.path.join(project_root, "calculator.py"),
        os.path.join(project_root, "src", "calculator.py"),
    ]
    content = None
    for p in candidates:
        if os.path.exists(p):
            content = _read(p)
            break
    if content is None:
        return False, "calculator.py not found"
    required = ["def add", "def subtract", "def multiply", "def divide"]
    missing = [fn for fn in required if fn not in content]
    if missing:
        return False, f"Missing functions: {', '.join(missing)}"
    return True, "calculator.py generated with all 4 functions"


# ---------------------------------------------------------------------------
# T6  Fix import error
# ---------------------------------------------------------------------------

_T6_APP = """\
from utils import helper

def main():
    return helper()
"""

_T6_UTILS = """\
def help_func():
    return 42
"""


def _t6_setup(project_root: str):
    _write(os.path.join(project_root, "src", "app.py"), _T6_APP)
    _write(os.path.join(project_root, "src", "utils.py"), _T6_UTILS)


def _t6_check(project_root: str, result: dict) -> tuple:
    app_path = os.path.join(project_root, "src", "app.py")
    utils_path = os.path.join(project_root, "src", "utils.py")
    if not os.path.exists(app_path):
        return False, "src/app.py not found"
    app_content = _read(app_path)
    utils_content = _read(utils_path) if os.path.exists(utils_path) else ""
    # Either app.py now imports help_func, or utils.py now exports helper
    if "help_func" in app_content:
        return True, "app.py updated to import help_func"
    if "def helper" in utils_content:
        return True, "utils.py updated to export helper"
    return False, "Import mismatch not resolved"


# ---------------------------------------------------------------------------
# T7  Generate login HTML page
# ---------------------------------------------------------------------------

def _t7_setup(project_root: str):
    os.makedirs(project_root, exist_ok=True)


def _t7_check(project_root: str, result: dict) -> tuple:
    candidates = [
        os.path.join(project_root, "login.html"),
        os.path.join(project_root, "src", "login.html"),
    ]
    content = None
    for p in candidates:
        if os.path.exists(p):
            content = _read(p)
            break
    if content is None:
        return False, "login.html not found"
    lower = content.lower()
    if "<input" not in lower:
        return False, "No <input> element found"
    if "<button" not in lower and "<form" not in lower:
        return False, "No <button> or <form> element found"
    return True, "login.html generated with inputs and button/form"


# ---------------------------------------------------------------------------
# T8  Fix indentation error
# ---------------------------------------------------------------------------

_T8_PROCESSOR_BUGGY = """\
def process(data):
    result = []
    for item in data:
    result.append(item * 2)
    return result
"""


def _t8_setup(project_root: str):
    _write(os.path.join(project_root, "src", "processor.py"), _T8_PROCESSOR_BUGGY)


def _t8_check(project_root: str, result: dict) -> tuple:
    path = os.path.join(project_root, "src", "processor.py")
    if not os.path.exists(path):
        return False, "src/processor.py not found"
    content = _read(path)
    lines = content.splitlines()
    # Find the line with result.append and verify it's indented under for
    for i, line in enumerate(lines):
        if "result.append" in line:
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if indent >= 8:  # at least 2 levels of indentation
                return True, "Indentation fixed"
            return False, f"result.append indent is {indent}, expected >= 8"
    return False, "result.append line not found"


# ---------------------------------------------------------------------------
# T9  Generate tests for sort function
# ---------------------------------------------------------------------------

_T9_SORTER = """\
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr
"""


def _t9_setup(project_root: str):
    _write(os.path.join(project_root, "src", "sorter.py"), _T9_SORTER)


def _t9_check(project_root: str, result: dict) -> tuple:
    tests_dir = os.path.join(project_root, "tests")
    if not os.path.isdir(tests_dir):
        return False, "tests/ directory not found"
    found = False
    for fname in os.listdir(tests_dir):
        if fname.endswith(".py"):
            content = _read(os.path.join(tests_dir, fname))
            if "def test_" in content and "bubble_sort" in content:
                found = True
                break
    if not found:
        return False, "No test file with 'def test_' and 'bubble_sort' found in tests/"
    return True, "Tests generated for bubble_sort"


# ---------------------------------------------------------------------------
# T10  Fix cross-file constant mismatch
# ---------------------------------------------------------------------------

_T10_CONFIG = """\
MAX_RETRIES = 3
TIMEOUT = 30
"""

_T10_MAIN = """\
from config import MAX_RETRY

def run():
    for i in range(MAX_RETRY):
        print(f"Attempt {i + 1}")
"""


def _t10_setup(project_root: str):
    _write(os.path.join(project_root, "src", "config.py"), _T10_CONFIG)
    _write(os.path.join(project_root, "src", "main.py"), _T10_MAIN)


def _t10_check(project_root: str, result: dict) -> tuple:
    main_path = os.path.join(project_root, "src", "main.py")
    config_path = os.path.join(project_root, "src", "config.py")
    if not os.path.exists(main_path):
        return False, "src/main.py not found"
    main_content = _read(main_path)
    config_content = _read(config_path) if os.path.exists(config_path) else ""
    # Either main.py now uses MAX_RETRIES, or config.py now exports MAX_RETRY
    if "MAX_RETRIES" in main_content and "MAX_RETRY " not in main_content.replace("MAX_RETRIES", ""):
        return True, "main.py updated to use MAX_RETRIES"
    if "MAX_RETRY " in config_content or "MAX_RETRY=" in config_content.replace(" ", ""):
        return True, "config.py updated to export MAX_RETRY"
    return False, "Constant name mismatch not resolved"


# ---------------------------------------------------------------------------
# Task list
# ---------------------------------------------------------------------------

GROUP1_TASKS = [
    {
        "id": "T1",
        "group": 1,
        "task": "修复 src/math_utils.py 中 fibonacci 函数的 bug，测试 fibonacci(6) 应该返回 8",
        "category": "bug_fix",
        "setup": _t1_setup,
        "check": _t1_check,
    },
    {
        "id": "T2",
        "group": 1,
        "task": "修复 src/billing.py 中 calculate_total 函数的变量名拼写错误",
        "category": "bug_fix",
        "setup": _t2_setup,
        "check": _t2_check,
    },
    {
        "id": "T3",
        "group": 1,
        "task": "在 src/string_utils.py 中添加一个 reverse_string 函数，接受字符串参数返回反转后的字符串",
        "category": "code_generation",
        "setup": _t3_setup,
        "check": _t3_check,
    },
    {
        "id": "T4",
        "group": 1,
        "task": "修复 src/checker.py 中 is_palindrome 函数，空字符串应该返回 True",
        "category": "bug_fix",
        "setup": _t4_setup,
        "check": _t4_check,
    },
    {
        "id": "T5",
        "group": 1,
        "task": "写一个 calculator.py 文件，包含 add, subtract, multiply, divide 四个函数",
        "category": "code_generation",
        "setup": _t5_setup,
        "check": _t5_check,
    },
    {
        "id": "T6",
        "group": 1,
        "task": "修复 src/app.py 的 import 错误，utils.py 中的函数名是 help_func 不是 helper",
        "category": "bug_fix",
        "setup": _t6_setup,
        "check": _t6_check,
    },
    {
        "id": "T7",
        "group": 1,
        "task": "写一个 login.html 登录页面，包含用户名和密码输入框以及登录按钮",
        "category": "code_generation",
        "setup": _t7_setup,
        "check": _t7_check,
    },
    {
        "id": "T8",
        "group": 1,
        "task": "修复 src/processor.py 中 process 函数的缩进错误",
        "category": "bug_fix",
        "setup": _t8_setup,
        "check": _t8_check,
    },
    {
        "id": "T9",
        "group": 1,
        "task": "为 src/sorter.py 中的 bubble_sort 函数生成 pytest 测试",
        "category": "code_generation",
        "setup": _t9_setup,
        "check": _t9_check,
    },
    {
        "id": "T10",
        "group": 1,
        "task": "修复 src/main.py 中的 import 错误，config.py 中的常量名是 MAX_RETRIES 不是 MAX_RETRY",
        "category": "bug_fix",
        "setup": _t10_setup,
        "check": _t10_check,
    },
]
