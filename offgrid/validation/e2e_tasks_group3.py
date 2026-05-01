"""Group 3: Complex + cross-file + extreme (stress scenarios)."""

import os


def _write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ── T21: Cross-file password hash fix ───────────────────────────────

_MODELS_PY = '''\
class User:
    def __init__(self, name, password):
        self.name = name
        self.password = password
'''

_AUTH_PY = '''\
from models import User


def save(user):
    pass


def register(name, pwd):
    user = User(name, pwd)
    save(user)
'''


def _setup_t21(project_root):
    _write_file(os.path.join(project_root, "src", "models.py"), _MODELS_PY)
    _write_file(os.path.join(project_root, "src", "auth.py"), _AUTH_PY)


def _check_t21(project_root, result):
    # Check all .py files in project for hash usage
    combined = ""
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in ('.offgrid', '__pycache__')]
        for fn in files:
            if fn.endswith('.py'):
                combined += _read_file(os.path.join(root, fn))
    if not combined:
        return False, "no .py files found"
    lower = combined.lower()
    if "hashlib" in lower or "hash(" in lower or "sha256" in lower or "md5" in lower or "bcrypt" in lower:
        return True, "ok"
    return False, "no hashlib or hash usage found"


# ── T22: Generate Flask API ─────────────────────────────────────────

def _setup_t22(project_root):
    pass


def _check_t22(project_root, result):
    # Flask API may be generated as app.py or app_1.py etc
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in ('.offgrid', '__pycache__')]
        for fn in files:
            if fn.endswith('.py') and not fn.startswith('__'):
                content = _read_file(os.path.join(root, fn))
                if ("flask" in content.lower() or "Flask" in content) and ("route" in content or "app" in content):
                    return True, "ok"
    return False, "no Flask app file found"


# ── T23: Ask tech news (chat+search) ────────────────────────────────

def _setup_t23(project_root):
    pass


def _check_t23(project_root, result):
    if not result.get("success"):
        return False, "result['success'] is not True"
    output = result.get("output", "")
    if not output.strip():
        return False, "output is empty"
    for kw in ("网站", "URL"):
        if kw in output:
            return False, f"output contains forbidden keyword: {kw}"
    return True, "ok"


# ── T24: Fix infinite recursion ─────────────────────────────────────

_TREE_PY = '''\
def flatten(nested):
    result = []
    for item in nested:
        result.extend(flatten(item))
    return result
'''


def _setup_t24(project_root):
    _write_file(os.path.join(project_root, "src", "tree.py"), _TREE_PY)


def _check_t24(project_root, result):
    path = os.path.join(project_root, "src", "tree.py")
    if not os.path.exists(path):
        return False, "src/tree.py not found"
    content = _read_file(path)
    has_guard = "isinstance" in content or "append(item)" in content
    has_recurse = "extend(flatten" in content or "extend( flatten" in content
    if not has_guard:
        return False, "missing isinstance check or append(item)"
    if not has_recurse:
        return False, "missing extend(flatten(...)) for recursive case"
    return True, "ok"


# ── T25: Generate TypeScript interface ──────────────────────────────

def _setup_t25(project_root):
    pass


def _check_t25(project_root, result):
    path = os.path.join(project_root, "types.ts")
    if not os.path.exists(path):
        return False, "types.ts not found"
    content = _read_file(path)
    if "interface" not in content and "type" not in content:
        return False, "types.ts missing interface/type keyword"
    if "User" not in content:
        return False, "types.ts missing User definition"
    return True, "ok"


# ── T26: Fix IndexError ─────────────────────────────────────────────

_PARSER_PY = '''\
def get_last_word(sentence):
    words = sentence.split()
    return words[len(words)]
'''


def _setup_t26(project_root):
    _write_file(os.path.join(project_root, "src", "parser.py"), _PARSER_PY)


def _check_t26(project_root, result):
    path = os.path.join(project_root, "src", "parser.py")
    if not os.path.exists(path):
        return False, "src/parser.py not found"
    content = _read_file(path)
    if any(kw in content for kw in ("words[-1]", "len(words) - 1", "len(words)-1")):
        return True, "ok"
    return False, "IndexError not fixed: missing words[-1] or len(words)-1"


# ── T27: Generate CSS file ──────────────────────────────────────────

def _setup_t27(project_root):
    pass


def _check_t27(project_root, result):
    path = os.path.join(project_root, "styles.css")
    if not os.path.exists(path):
        return False, "styles.css not found"
    content = _read_file(path)
    for kw in ("body", "header", "{", "}"):
        if kw not in content:
            return False, f"styles.css missing '{kw}'"
    return True, "ok"


# ── T28: Refactor extract common code ───────────────────────────────

_REPORTS_PY = '''\
def generate_pdf(data):
    if not data:
        raise ValueError("empty")
    if not isinstance(data, dict):
        raise TypeError("need dict")
    # pdf specific logic
    return "pdf"


def generate_csv(data):
    if not data:
        raise ValueError("empty")
    if not isinstance(data, dict):
        raise TypeError("need dict")
    # csv specific logic
    return "csv"
'''


def _setup_t28(project_root):
    _write_file(os.path.join(project_root, "src", "reports.py"), _REPORTS_PY)


def _check_t28(project_root, result):
    path = os.path.join(project_root, "src", "reports.py")
    if not os.path.exists(path):
        return False, "src/reports.py not found"
    content = _read_file(path)
    if "def validate_data" not in content:
        return False, "validate_data function not found"
    return True, "ok"


# ── T29: Generate Go hello world ────────────────────────────────────

def _setup_t29(project_root):
    pass


def _check_t29(project_root, result):
    path = os.path.join(project_root, "main.go")
    if not os.path.exists(path):
        return False, "main.go not found"
    content = _read_file(path)
    for kw in ("package main", "func main", "fmt"):
        if kw not in content:
            return False, f"main.go missing '{kw}'"
    return True, "ok"


# ── T30: Fix missing await ──────────────────────────────────────────

_FETCHER_PY = '''\
import asyncio


async def fetch_data(url):
    await asyncio.sleep(1)
    return {"url": url, "data": "ok"}


async def fetch_all(urls):
    results = []
    for url in urls:
        result = fetch_data(url)
        results.append(result)
    return results
'''


def _setup_t30(project_root):
    _write_file(os.path.join(project_root, "src", "fetcher.py"), _FETCHER_PY)


def _check_t30(project_root, result):
    path = os.path.join(project_root, "src", "fetcher.py")
    if not os.path.exists(path):
        return False, "src/fetcher.py not found"
    content = _read_file(path)
    if "await fetch_data" in content:
        return True, "ok"
    # LLM may have rewritten the function differently but still correct
    if "await" in content and "fetch_data" in content:
        return True, "ok (await present)"
    return False, "missing 'await fetch_data'"


# ── Export ───────────────────────────────────────────────────────────

GROUP3_TASKS = [
    {
        "id": "T21",
        "group": 3,
        "task": "修复安全问题：src/models.py 中密码是明文存储的，应该用 hashlib 进行 hash 处理",
        "category": "fix",
        "setup": _setup_t21,
        "check": _check_t21,
    },
    {
        "id": "T22",
        "group": 3,
        "task": "写一个 app.py Flask API，包含 GET /users, POST /users, GET /users/<id> 三个接口",
        "category": "codegen",
        "setup": _setup_t22,
        "check": _check_t22,
    },
    {
        "id": "T23",
        "group": 3,
        "task": "最近有什么重要的科技新闻",
        "category": "chat",
        "setup": _setup_t23,
        "check": _check_t23,
    },
    {
        "id": "T24",
        "group": 3,
        "task": "修复 src/tree.py 中 flatten 函数的无限递归 bug，非列表元素应该直接 append",
        "category": "fix",
        "setup": _setup_t24,
        "check": _check_t24,
    },
    {
        "id": "T25",
        "group": 3,
        "task": "写一个 types.ts TypeScript 文件，定义 User 接口包含 id(number), name(string), email(string) 字段",
        "category": "codegen",
        "setup": _setup_t25,
        "check": _check_t25,
    },
    {
        "id": "T26",
        "group": 3,
        "task": "修复 src/parser.py 中 get_last_word 函数的 IndexError，数组越界了",
        "category": "fix",
        "setup": _setup_t26,
        "check": _check_t26,
    },
    {
        "id": "T27",
        "group": 3,
        "task": "写一个 styles.css 样式文件，包含 body, header, main, footer 的基本布局样式",
        "category": "codegen",
        "setup": _setup_t27,
        "check": _check_t27,
    },
    {
        "id": "T28",
        "group": 3,
        "task": "重构 src/reports.py，把 generate_pdf 和 generate_csv 中重复的验证逻辑提取为 validate_data 函数",
        "category": "refactor",
        "setup": _setup_t28,
        "check": _check_t28,
    },
    {
        "id": "T29",
        "group": 3,
        "task": "写一个 main.go 文件，Go 语言的 hello world 程序",
        "category": "codegen",
        "setup": _setup_t29,
        "check": _check_t29,
    },
    {
        "id": "T30",
        "group": 3,
        "task": "修复 src/fetcher.py 中 fetch_all 函数缺少 await 的问题",
        "category": "fix",
        "setup": _setup_t30,
        "check": _check_t30,
    },
]
