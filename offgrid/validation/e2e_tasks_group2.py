"""Group 2: Chat + search + boundary (vibe coding scenarios)."""

import os
import json


def _write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ── T11: Ask weather (chat+search) ──────────────────────────────────

def _setup_t11(project_root):
    pass


def _check_t11(project_root, result):
    if not result.get("success"):
        return False, "result['success'] is not True"
    output = result.get("output", "")
    if not output.strip():
        return False, "output is empty"
    for kw in ("网站", "URL", "http"):
        if kw in output:
            return False, f"output contains forbidden keyword: {kw}"
    return True, "ok"


# ── T12: Greeting ───────────────────────────────────────────────────

def _setup_t12(project_root):
    pass


def _check_t12(project_root, result):
    if not result.get("success"):
        return False, "result['success'] is not True"
    if not result.get("output", "").strip():
        return False, "output is empty"
    return True, "ok"


# ── T13: Knowledge question ─────────────────────────────────────────

def _setup_t13(project_root):
    pass


def _check_t13(project_root, result):
    if not result.get("success"):
        return False, "result['success'] is not True"
    output = result.get("output", "")
    keywords = ("GIL", "全局", "锁", "Global", "Lock")
    if not any(kw in output for kw in keywords):
        return False, f"output does not contain any of {keywords}"
    return True, "ok"


# ── T14: Generate weather HTML page ─────────────────────────────────

def _setup_t14(project_root):
    pass


def _check_t14(project_root, result):
    # look for weather.html or weather_N.html
    found = None
    for name in os.listdir(project_root):
        if name.startswith("weather") and name.endswith(".html"):
            found = os.path.join(project_root, name)
            break
    if found is None:
        return False, "weather.html not found"
    content = _read_file(found)
    if "<html" not in content.lower() and "<!doctype" not in content.lower():
        return False, "file does not contain <html or <!DOCTYPE"
    return True, "ok"


# ── T15: Refactor long function ─────────────────────────────────────

_HANDLER_PY = '''\
def handle_request(request):
    # --- validation ---
    if not request:
        raise ValueError("request is empty")
    if not isinstance(request, dict):
        raise TypeError("request must be dict")
    if "action" not in request:
        raise KeyError("missing action")
    if "payload" not in request:
        raise KeyError("missing payload")
    action = request["action"]
    if action not in ("create", "update", "delete"):
        raise ValueError(f"unknown action: {action}")
    payload = request["payload"]
    if not isinstance(payload, dict):
        raise TypeError("payload must be dict")
    if "id" not in payload:
        raise KeyError("missing id in payload")

    # --- processing ---
    result = {}
    if action == "create":
        result["status"] = "created"
        result["id"] = payload["id"]
        result["data"] = payload
    elif action == "update":
        result["status"] = "updated"
        result["id"] = payload["id"]
        result["data"] = payload
    elif action == "delete":
        result["status"] = "deleted"
        result["id"] = payload["id"]

    # --- formatting ---
    output = f"[{result['status'].upper()}] id={result['id']}"
    if "data" in result:
        output += f" fields={len(result['data'])}"
    return {"message": output, "result": result}
'''


def _setup_t15(project_root):
    _write_file(os.path.join(project_root, "src", "handler.py"), _HANDLER_PY)


def _check_t15(project_root, result):
    path = os.path.join(project_root, "src", "handler.py")
    if not os.path.exists(path):
        return False, "src/handler.py not found"
    content = _read_file(path)
    if "def handle_request" not in content:
        return False, "handle_request function missing"
    if "def validate_input" not in content:
        return False, "validate_input function missing"
    return True, "ok"


# ── T16: Add docstring ──────────────────────────────────────────────

_MATH_OPS_PY = '''\
def gcd(a, b):
    while b:
        a, b = b, a % b
    return a
'''


def _setup_t16(project_root):
    _write_file(os.path.join(project_root, "src", "math_ops.py"), _MATH_OPS_PY)


def _check_t16(project_root, result):
    # doc pipeline: locator finds file, generator modifies it
    # Check if any .py file in project contains docstring for gcd
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in ('.offgrid', '__pycache__')]
        for fn in files:
            if fn.endswith('.py'):
                path = os.path.join(root, fn)
                content = _read_file(path)
                if ('"""' in content or "'''" in content) and 'def gcd' in content:
                    return True, "ok"
    return False, "no docstring found after def gcd"


# ── T17: Generate shell script ──────────────────────────────────────

def _setup_t17(project_root):
    pass


def _check_t17(project_root, result):
    path = os.path.join(project_root, "backup.sh")
    if not os.path.exists(path):
        return False, "backup.sh not found"
    content = _read_file(path)
    if not any(kw in content for kw in ("cp", "rsync", "*.py")):
        return False, "backup.sh does not contain cp/rsync/*.py"
    return True, "ok"


# ── T18: Ambiguous input ────────────────────────────────────────────

_APP_PY = '''\
def hello(name):
    return f"Hello, {name}!"
'''


def _setup_t18(project_root):
    _write_file(os.path.join(project_root, "src", "app.py"), _APP_PY)


def _check_t18(project_root, result):
    # Ambiguous input — as long as it doesn't crash, it's acceptable
    # May be routed to chat (success=True) or locator_repair (may fail after retries)
    if result.get("success"):
        return True, "ok"
    # Even if pipeline failed, as long as it returned a result (not exception), it's ok
    if result.get("error") is not None:
        return True, "ok (pipeline failed gracefully)"
    return False, "result['success'] is not True (agent crashed)"


# ── T19: Generate JSON config ───────────────────────────────────────

def _setup_t19(project_root):
    pass


def _check_t19(project_root, result):
    path = os.path.join(project_root, "config.json")
    if not os.path.exists(path):
        return False, "config.json not found"
    content = _read_file(path)
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        return False, f"config.json is not valid JSON: {e}"
    if not any(kw in content for kw in ("database", "host", "port")):
        return False, "config.json missing database/host/port"
    return True, "ok"


# ── T20: Fix missing return ─────────────────────────────────────────

_VALIDATOR_PY = '''\
def is_valid_email(email):
    if '@' in email and '.' in email:
        result = True
    else:
        result = False
'''


def _setup_t20(project_root):
    _write_file(os.path.join(project_root, "src", "validator.py"), _VALIDATOR_PY)


def _check_t20(project_root, result):
    path = os.path.join(project_root, "src", "validator.py")
    if not os.path.exists(path):
        return False, "src/validator.py not found"
    content = _read_file(path)
    if any(kw in content for kw in ("return result", "return True", "return False")):
        return True, "ok"
    return False, "missing return statement"


# ── Export ───────────────────────────────────────────────────────────

GROUP2_TASKS = [
    {
        "id": "T11",
        "group": 2,
        "task": "今天南京天气怎么样",
        "category": "chat",
        "setup": _setup_t11,
        "check": _check_t11,
    },
    {
        "id": "T12",
        "group": 2,
        "task": "你好",
        "category": "chat",
        "setup": _setup_t12,
        "check": _check_t12,
    },
    {
        "id": "T13",
        "group": 2,
        "task": "Python的GIL是什么？简单解释一下",
        "category": "chat",
        "setup": _setup_t13,
        "check": _check_t13,
    },
    {
        "id": "T14",
        "group": 2,
        "task": "写一个 weather.html 页面展示天气信息",
        "category": "codegen",
        "setup": _setup_t14,
        "check": _check_t14,
    },
    {
        "id": "T15",
        "group": 2,
        "task": "重构 src/handler.py 中的 handle_request 函数，把验证逻辑拆分到单独的 validate_input 函数",
        "category": "refactor",
        "setup": _setup_t15,
        "check": _check_t15,
    },
    {
        "id": "T16",
        "group": 2,
        "task": "给 src/math_ops.py 中的 gcd 函数添加 docstring",
        "category": "doc",
        "setup": _setup_t16,
        "check": _check_t16,
    },
    {
        "id": "T17",
        "group": 2,
        "task": "写一个 backup.sh 脚本，将当前目录的所有 .py 文件复制到 backup/ 目录",
        "category": "codegen",
        "setup": _setup_t17,
        "check": _check_t17,
    },
    {
        "id": "T18",
        "group": 2,
        "task": "帮我看看 src/app.py 这段代码有什么问题",
        "category": "chat",
        "setup": _setup_t18,
        "check": _check_t18,
    },
    {
        "id": "T19",
        "group": 2,
        "task": "生成一个 config.json 配置文件，包含 database host/port/name 和 server port 字段",
        "category": "codegen",
        "setup": _setup_t19,
        "check": _check_t19,
    },
    {
        "id": "T20",
        "group": 2,
        "task": "修复 src/validator.py 中 is_valid_email 函数缺少 return 语句的问题",
        "category": "fix",
        "setup": _setup_t20,
        "check": _check_t20,
    },
]
