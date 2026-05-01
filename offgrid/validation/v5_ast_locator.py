"""
V5 验证：AST Locator vs LLM 文件树猜测对比。
目标：比较 tree-sitter 调用图定位（B组）vs 当前 LLM 文件树猜测（A组）。
红线：B组函数级提升 < 15% → 触发 FLEX-4，推迟 AST 调用图。

A组需要 Ollama 在线。B组使用 tree-sitter ASTLocator，无需 LLM。

用法：
  python -m offgrid.validation.v5_ast_locator --ollama-model gemma3:4b
"""

import argparse
import io
import json
import os
import sys
import tempfile
import time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── 10 个 bug case（复用 V3 的场景结构，独立定义）──────────────────
BUG_CASES = [
    {
        "id": 1,
        "description": "用户登录时密码校验总是返回False",
        "file_tree": """project/
  src/
    auth/
      login.py
      jwt_utils.py
      password.py
    models/
      user.py
    api/
      routes.py
  tests/
    test_auth.py
  config.py""",
        "file_contents": {
            "src/auth/password.py": (
                "import hashlib\n\n"
                "def hash_password(password: str) -> str:\n"
                "    return hashlib.sha256(password.encode()).hexdigest()\n\n"
                "def verify_password(password: str, hashed: str) -> bool:\n"
                "    # BUG: timing-safe compare missing\n"
                "    return hash_password(password) == hashed\n"
            ),
        },
        "expected_file": "src/auth/password.py",
        "expected_function": "verify_password",
    },
    {
        "id": 2,
        "description": "API分页查询返回的total_count总是0",
        "file_tree": """project/
  src/
    api/
      views.py
      serializers.py
      pagination.py
    db/
      queries.py
      models.py
  tests/
    test_views.py""",
        "file_contents": {
            "src/api/pagination.py": (
                "from dataclasses import dataclass\n\n"
                "@dataclass\nclass PageResult:\n"
                "    items: list\n    total_count: int\n    page: int\n    page_size: int\n\n"
                "def paginate(query_result, page=1, page_size=20):\n"
                "    start = (page - 1) * page_size\n"
                "    items = query_result[start:start + page_size]\n"
                "    return PageResult(items=items, total_count=len(items), page=page, page_size=page_size)\n"
            ),
        },
        "expected_file": "src/api/pagination.py",
        "expected_function": "paginate",
    },
    {
        "id": 3,
        "description": "文件上传后文件名变成乱码",
        "file_tree": """project/
  src/
    upload/
      handler.py
      storage.py
      validators.py
    api/
      routes.py
    utils/
      file_utils.py
  config.py""",
        "file_contents": {
            "src/upload/handler.py": (
                "import os, uuid\n\n"
                "def handle_upload(file_data, original_filename: str) -> str:\n"
                "    safe_name = original_filename.replace(' ', '_')\n"
                "    new_name = f'{uuid.uuid4().hex}_{safe_name}'\n"
                "    return save_file(file_data, new_name)\n\n"
                "def save_file(data, filename: str) -> str:\n"
                "    path = os.path.join('/uploads', filename)\n"
                "    with open(path, 'wb') as f:\n        f.write(data)\n"
                "    return path\n"
            ),
        },
        "expected_file": "src/upload/handler.py",
        "expected_function": "handle_upload",
    },
    {
        "id": 4,
        "description": "缓存过期后没有自动刷新，一直返回旧数据",
        "file_tree": """project/
  src/
    cache/
      redis_cache.py
      memory_cache.py
      decorators.py
    services/
      user_service.py
  config.py""",
        "file_contents": {
            "src/cache/memory_cache.py": (
                "import time\nfrom typing import Any, Optional\n\n"
                "class MemoryCache:\n"
                "    def __init__(self):\n        self._store = {}\n\n"
                "    def get(self, key: str) -> Optional[Any]:\n"
                "        entry = self._store.get(key)\n"
                "        if entry is None:\n            return None\n"
                "        value, expire_at = entry\n"
                "        if time.time() > expire_at:\n"
                "            return value  # BUG: should return None\n"
                "        return value\n\n"
                "    def set(self, key: str, value: Any, ttl: int = 300):\n"
                "        self._store[key] = (value, time.time() + ttl)\n"
            ),
        },
        "expected_file": "src/cache/memory_cache.py",
        "expected_function": "get",
    },
    {
        "id": 5,
        "description": "WebSocket断开后客户端没有收到通知",
        "file_tree": """project/
  src/
    websocket/
      manager.py
      handlers.py
      events.py
    api/
      routes.py
    models/
      connection.py
  main.py""",
        "file_contents": {
            "src/websocket/manager.py": (
                "from typing import Dict, Set\nimport asyncio\n\n"
                "class ConnectionManager:\n"
                "    def __init__(self):\n"
                "        self.active: Dict[str, object] = {}\n"
                "        self.rooms: Dict[str, Set[str]] = {}\n\n"
                "    async def connect(self, ws, user_id: str):\n"
                "        self.active[user_id] = ws\n\n"
                "    async def disconnect(self, user_id: str):\n"
                "        # BUG: no notification to room members\n"
                "        self.active.pop(user_id, None)\n"
                "        for room, members in self.rooms.items():\n"
                "            members.discard(user_id)\n"
            ),
        },
        "expected_file": "src/websocket/manager.py",
        "expected_function": "disconnect",
    },
    {
        "id": 6,
        "description": "日期格式转换在不同时区下结果不一致",
        "file_tree": """project/
  src/
    utils/
      date_utils.py
      formatters.py
      validators.py
    api/
      views.py
    models/
      event.py
  config.py""",
        "file_contents": {
            "src/utils/date_utils.py": (
                "from datetime import datetime\n\n"
                "def parse_date(date_str: str) -> datetime:\n"
                "    # BUG: no timezone handling\n"
                "    return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')\n\n"
                "def format_date(dt: datetime, fmt: str = '%Y-%m-%d') -> str:\n"
                "    return dt.strftime(fmt)\n"
            ),
        },
        "expected_file": "src/utils/date_utils.py",
        "expected_function": "parse_date",
    },
    {
        "id": 7,
        "description": "并发创建订单时出现库存超卖",
        "file_tree": """project/
  src/
    orders/
      service.py
      models.py
      validators.py
    inventory/
      stock.py
      models.py
    db/
      session.py
  main.py""",
        "file_contents": {
            "src/inventory/stock.py": (
                "class StockManager:\n"
                "    def __init__(self, db):\n        self.db = db\n\n"
                "    def check_stock(self, product_id: int) -> int:\n"
                "        row = self.db.query('SELECT quantity FROM stock WHERE product_id = ?', product_id)\n"
                "        return row['quantity'] if row else 0\n\n"
                "    def deduct_stock(self, product_id: int, amount: int) -> bool:\n"
                "        # BUG: no database lock, race condition\n"
                "        current = self.check_stock(product_id)\n"
                "        if current >= amount:\n"
                "            self.db.execute('UPDATE stock SET quantity = quantity - ? WHERE product_id = ?', amount, product_id)\n"
                "            return True\n"
                "        return False\n"
            ),
        },
        "expected_file": "src/inventory/stock.py",
        "expected_function": "deduct_stock",
    },
    {
        "id": 8,
        "description": "配置文件中的环境变量没有被正确替换",
        "file_tree": """project/
  src/
    config/
      loader.py
      parser.py
      defaults.py
    app/
      main.py
      settings.py
  config.yaml
  .env""",
        "file_contents": {
            "src/config/loader.py": (
                "import os, re, yaml\n\n"
                "def load_config(path: str) -> dict:\n"
                "    with open(path, 'r') as f:\n        raw = f.read()\n"
                "    config = yaml.safe_load(raw)\n"
                "    return _resolve_env(config)\n\n"
                "def _resolve_env(obj):\n"
                "    if isinstance(obj, str):\n"
                "        pattern = r'\\\\$([A-Z_]+)'\n"
                "        def replacer(m):\n"
                "            return os.environ.get(m.group(1), m.group(0))\n"
                "        return re.sub(pattern, replacer, obj)\n"
                "    elif isinstance(obj, dict):\n"
                "        return {k: _resolve_env(v) for k, v in obj.items()}\n"
                "    elif isinstance(obj, list):\n"
                "        return [_resolve_env(i) for i in obj]\n"
                "    return obj\n"
            ),
        },
        "expected_file": "src/config/loader.py",
        "expected_function": "_resolve_env",
    },
    {
        "id": 9,
        "description": "邮件发送功能在附件大于5MB时静默失败",
        "file_tree": """project/
  src/
    notifications/
      email_sender.py
      templates.py
      queue.py
    utils/
      file_utils.py
  config.py""",
        "file_contents": {
            "src/notifications/email_sender.py": (
                "import smtplib\nfrom email.mime.multipart import MIMEMultipart\n"
                "from email.mime.base import MIMEBase\n\n"
                "class EmailSender:\n"
                "    def __init__(self, smtp_host, smtp_port, username, password):\n"
                "        self.smtp_host = smtp_host\n"
                "        self.smtp_port = smtp_port\n\n"
                "    def send(self, to, subject, body, attachments=None):\n"
                "        msg = MIMEMultipart()\n"
                "        msg['To'] = to\n"
                "        msg['Subject'] = subject\n"
                "        if attachments:\n"
                "            for filepath in attachments:\n"
                "                part = MIMEBase('application', 'octet-stream')\n"
                "                with open(filepath, 'rb') as f:\n"
                "                    part.set_payload(f.read())\n"
                "                msg.attach(part)\n"
                "        try:\n"
                "            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:\n"
                "                server.send_message(msg)\n"
                "        except Exception:\n"
                "            pass  # BUG: silently swallows exception\n"
            ),
        },
        "expected_file": "src/notifications/email_sender.py",
        "expected_function": "send",
    },
    {
        "id": 10,
        "description": "数据导出CSV时中文列名显示为乱码",
        "file_tree": """project/
  src/
    export/
      csv_exporter.py
      excel_exporter.py
      formatters.py
    api/
      views.py
    models/
      report.py
  main.py""",
        "file_contents": {
            "src/export/csv_exporter.py": (
                "import csv, io\n\n"
                "def export_csv(data: list, filename: str) -> bytes:\n"
                "    if not data:\n        return b''\n"
                "    output = io.StringIO()\n"
                "    writer = csv.DictWriter(output, fieldnames=data[0].keys())\n"
                "    writer.writeheader()\n"
                "    writer.writerows(data)\n"
                "    # BUG: ascii encoding, should be utf-8-sig for Excel\n"
                "    return output.getvalue().encode('ascii', errors='replace')\n\n"
                "def export_csv_file(data: list, filepath: str):\n"
                "    content = export_csv(data, filepath)\n"
                "    with open(filepath, 'wb') as f:\n        f.write(content)\n"
            ),
        },
        "expected_file": "src/export/csv_exporter.py",
        "expected_function": "export_csv",
    },
]


def _create_project(tmpdir: str, case: dict):
    """Create a temporary project structure for a test case."""
    for line in case["file_tree"].strip().split("\n"):
        stripped = line.rstrip()
        if not stripped:
            continue
        indent = len(stripped) - len(stripped.lstrip())
        name = stripped.strip().rstrip("/")
        if not name:
            continue

    # Create files with content
    for fpath, content in case.get("file_contents", {}).items():
        full_path = os.path.join(tmpdir, fpath)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

    # Create empty placeholder files from tree
    _create_tree_files(tmpdir, case["file_tree"])


def _create_tree_files(tmpdir: str, tree_text: str):
    """Parse indented file tree and create actual files/dirs."""
    lines = tree_text.strip().split("\n")
    path_stack = []

    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            continue
        indent = len(stripped) - len(stripped.lstrip())
        depth = indent // 2
        name = stripped.strip().rstrip("/")

        path_stack = path_stack[:depth]
        path_stack.append(name)

        full_path = os.path.join(tmpdir, *path_stack)

        if stripped.rstrip().endswith("/"):
            os.makedirs(full_path, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            if not os.path.exists(full_path):
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(f"# {name}\n")


def run_group_a(llm, cases: list[dict]) -> list[dict]:
    """
    Group A: current LLM file-tree guessing approach (LocatorExpert).
    Returns list of {case_id, file_hit, func_hit, elapsed_s}.
    """
    from offgrid.experts.locator import LocatorExpert
    from offgrid.tools.executor import ToolExecutor
    from offgrid.core.context import TaskContext

    results = []
    for case in cases:
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_project(tmpdir, case)
            tools = ToolExecutor(project_root=tmpdir)
            locator = LocatorExpert(llm=llm, tool_executor=tools)
            ctx = TaskContext(
                user_input=case["description"],
                project_root=tmpdir,
            )

            t0 = time.time()
            result = locator.run(ctx)
            elapsed = time.time() - t0

            file_hit = False
            func_hit = False
            if result:
                found_files = [f.replace("\\", "/").lstrip("./") for f in result.get("relevant_files", [])]
                found_funcs = result.get("relevant_functions", [])
                file_hit = any(case["expected_file"] in ff or ff.endswith(case["expected_file"]) for ff in found_files)
                func_hit = case["expected_function"] in found_funcs

            r = {
                "case_id": case["id"],
                "file_hit": file_hit,
                "func_hit": func_hit,
                "elapsed_s": round(elapsed, 1),
            }
            results.append(r)

            f_icon = "OK" if file_hit else "FAIL"
            fn_icon = "OK" if func_hit else "FAIL"
            print(f"    [A] Case {case['id']:2d}: file={f_icon} func={fn_icon} ({elapsed:.1f}s)")

    return results


def run_group_b(llm, cases: list[dict]) -> list[dict] | None:
    """
    Group B: tree-sitter call graph locating (ASTLocator).
    Returns list of {case_id, file_hit, func_hit, elapsed_s}.
    """
    try:
        from offgrid.ast_engine.locator import ASTLocator
    except ImportError as e:
        print(f"    [B] tree-sitter 未安装，B组跳过 ({e})")
        return None

    locator = ASTLocator()
    results = []

    for case in cases:
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_project(tmpdir, case)

            t0 = time.time()
            result = locator.locate(tmpdir, case["description"])
            elapsed = time.time() - t0

            file_hit = False
            func_hit = False
            if result:
                found_files = [f.replace("\\", "/").lstrip("./") for f in result.get("relevant_files", [])]
                found_funcs = result.get("relevant_functions", [])
                # Also accept short names (strip class prefix)
                found_funcs_short = list(found_funcs)
                for fn in found_funcs:
                    if "." in fn:
                        found_funcs_short.append(fn.split(".")[-1])

                file_hit = any(
                    case["expected_file"] in ff or ff.endswith(case["expected_file"])
                    for ff in found_files
                )
                func_hit = case["expected_function"] in found_funcs_short

            r = {
                "case_id": case["id"],
                "file_hit": file_hit,
                "func_hit": func_hit,
                "elapsed_s": round(elapsed, 3),
            }
            results.append(r)

            f_icon = "OK" if file_hit else "FAIL"
            fn_icon = "OK" if func_hit else "FAIL"
            print(f"    [B] Case {case['id']:2d}: file={f_icon} func={fn_icon} ({elapsed:.3f}s)")

    return results


def run_validation(ollama_model: str = "gemma3:4b"):
    from offgrid.llm.llama_backend import LLMBackend

    print("=" * 60)
    print("V5 验证：AST Locator vs LLM 文件树猜测")
    print("=" * 60)
    print(f"模型: {ollama_model}")
    print(f"测试用例: {len(BUG_CASES)} 个")
    print()

    llm = LLMBackend(ollama_model=ollama_model)

    # ── Group A: LLM file tree guessing ──
    print("── Group A: LLM 文件树猜测 (LocatorExpert) ──")
    ollama_available = True
    try:
        import httpx
        resp = httpx.get(f"http://localhost:11434/api/tags", timeout=3.0)
        if resp.status_code != 200:
            ollama_available = False
    except Exception:
        ollama_available = False

    group_a_results = None
    if ollama_available:
        group_a_results = run_group_a(llm, BUG_CASES)
    else:
        print("    Ollama 不在线，A组跳过")

    # ── Group B: tree-sitter call graph (ASTLocator) ──
    print()
    print("── Group B: tree-sitter 调用图定位 (ASTLocator) ──")
    group_b_results = run_group_b(llm, BUG_CASES)

    # ── Compare & conclude ──
    print()
    print("=" * 60)
    print("验证结论")
    print("=" * 60)

    a_file_acc = None
    a_func_acc = None
    if group_a_results:
        a_file_hits = sum(1 for r in group_a_results if r["file_hit"])
        a_func_hits = sum(1 for r in group_a_results if r["func_hit"])
        a_file_acc = a_file_hits / len(BUG_CASES) * 100
        a_func_acc = a_func_hits / len(BUG_CASES) * 100
        print(f"  A组 文件级准确率: {a_file_hits}/{len(BUG_CASES)} = {a_file_acc:.0f}%")
        print(f"  A组 函数级准确率: {a_func_hits}/{len(BUG_CASES)} = {a_func_acc:.0f}%")
    else:
        print("  A组: 未运行 (Ollama 离线)")

    b_file_acc = None
    b_func_acc = None
    if group_b_results:
        b_file_hits = sum(1 for r in group_b_results if r["file_hit"])
        b_func_hits = sum(1 for r in group_b_results if r["func_hit"])
        b_file_acc = b_file_hits / len(BUG_CASES) * 100
        b_func_acc = b_func_hits / len(BUG_CASES) * 100
        file_improvement = b_file_acc - (a_file_acc or 0)
        func_improvement = b_func_acc - (a_func_acc or 0)
        print(f"  B组 文件级准确率: {b_file_hits}/{len(BUG_CASES)} = {b_file_acc:.0f}%")
        print(f"  B组 函数级准确率: {b_func_hits}/{len(BUG_CASES)} = {b_func_acc:.0f}%")
        if a_func_acc is not None:
            print(f"  函数级提升: {func_improvement:+.0f}%")
            if func_improvement < 15:
                print("  判定: 函数级提升 < 15%，触发 FLEX-4，推迟 AST 调用图")
            else:
                print("  判定: 函数级提升 >= 15%，AST 调用图值得集成")
        else:
            print("  判定: A组未运行，无法比较")
    else:
        print("  B组: 未运行 (tree-sitter 不可用)")
        print("  判定: 待 tree-sitter 集成后重新运行")

    V5_CONCLUSION = {
        "group_a": {
            "method": "LLM file tree guessing (LocatorExpert)",
            "file_accuracy": a_file_acc,
            "func_accuracy": a_func_acc,
            "results": group_a_results,
        },
        "group_b": {
            "method": "tree-sitter call graph (ASTLocator)",
            "file_accuracy": b_file_acc,
            "func_accuracy": b_func_acc,
            "results": group_b_results,
        },
        "comparison": {
            "file_improvement_pct": (b_file_acc - a_file_acc) if (b_file_acc is not None and a_file_acc is not None) else None,
            "func_improvement_pct": (b_func_acc - a_func_acc) if (b_func_acc is not None and a_func_acc is not None) else None,
            "flex4_triggered": (b_func_acc - a_func_acc < 15) if (b_func_acc is not None and a_func_acc is not None) else None,
        },
        "total_cases": len(BUG_CASES),
    }

    conclusion_path = os.path.join(os.path.dirname(__file__), "v5_conclusion.json")
    with open(conclusion_path, "w", encoding="utf-8") as f:
        json.dump(V5_CONCLUSION, f, indent=2, ensure_ascii=False)
    print(f"\n  结论已保存到: {conclusion_path}")

    return V5_CONCLUSION


def main():
    parser = argparse.ArgumentParser(description="V5 AST Locator vs LLM 文件树猜测验证")
    parser.add_argument("--ollama-model", type=str, default="gemma3:4b")
    args = parser.parse_args()
    run_validation(ollama_model=args.ollama_model)


if __name__ == "__main__":
    main()
