"""
V3 验证：Locator 定位精度测试。
目标：确认本地模型做层级定位（文件→函数）的准确率。
红线：文件级准确率 < 60% 则触发 FLEX-2（退到两层定位）。

用法：
  python -m offgrid.validation.v3_locator_accuracy --ollama-model qwen3-8b
"""

import argparse
import json
import os
import sys
import tempfile
import time

# ── 10 个测试 case（模拟真实 bug 修复场景）──────────────────
TEST_CASES = [
    {
        "id": 1,
        "description": "用户登录时密码校验总是返回False，即使密码正确",
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
      middleware.py
  tests/
    test_auth.py
    test_api.py
  config.py
  main.py""",
        "expected_files": ["src/auth/password.py", "src/auth/login.py"],
        "file_contents": {
            "src/auth/password.py": '''import hashlib

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    # BUG: 比较时用了 == 而不是 hmac.compare_digest
    return hash_password(password) == hashed

def validate_strength(password: str) -> bool:
    return len(password) >= 8
''',
        },
        "expected_functions": ["verify_password"],
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
    utils/
      helpers.py
  tests/
    test_views.py
  main.py""",
        "expected_files": ["src/api/pagination.py", "src/db/queries.py"],
        "file_contents": {
            "src/api/pagination.py": '''from dataclasses import dataclass

@dataclass
class PageResult:
    items: list
    total_count: int
    page: int
    page_size: int

def paginate(query_result, page: int = 1, page_size: int = 20) -> PageResult:
    start = (page - 1) * page_size
    items = query_result[start:start + page_size]
    # BUG: total_count 应该是 len(query_result) 而不是 len(items)
    return PageResult(items=items, total_count=len(items), page=page, page_size=page_size)
''',
        },
        "expected_functions": ["paginate"],
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
        "expected_files": ["src/upload/handler.py", "src/upload/storage.py"],
        "file_contents": {
            "src/upload/handler.py": '''import os
import uuid

def handle_upload(file_data, original_filename: str) -> str:
    ext = os.path.splitext(original_filename)[1]
    # BUG: 中文文件名没有做 URL 编码
    safe_name = original_filename.replace(" ", "_")
    new_name = f"{uuid.uuid4().hex}_{safe_name}"
    return save_file(file_data, new_name)

def save_file(data, filename: str) -> str:
    path = os.path.join("/uploads", filename)
    with open(path, "wb") as f:
        f.write(data)
    return path
''',
        },
        "expected_functions": ["handle_upload"],
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
      product_service.py
    config.py""",
        "expected_files": ["src/cache/memory_cache.py", "src/cache/decorators.py"],
        "file_contents": {
            "src/cache/memory_cache.py": '''import time
from typing import Any, Optional

class MemoryCache:
    def __init__(self):
        self._store = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expire_at = entry
        # BUG: 过期判断用了 > 而不是 <
        if time.time() > expire_at:
            return value  # 应该返回 None 并删除
        return value

    def set(self, key: str, value: Any, ttl: int = 300):
        self._store[key] = (value, time.time() + ttl)

    def delete(self, key: str):
        self._store.pop(key, None)
''',
        },
        "expected_functions": ["get"],
    },
    {
        "id": 5,
        "description": "WebSocket连接断开后客户端没有收到通知",
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
        "expected_files": ["src/websocket/manager.py", "src/websocket/handlers.py"],
        "file_contents": {
            "src/websocket/manager.py": '''from typing import Dict, Set
import asyncio

class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, object] = {}
        self.rooms: Dict[str, Set[str]] = {}

    async def connect(self, ws, user_id: str):
        self.active[user_id] = ws

    async def disconnect(self, user_id: str):
        # BUG: 断开时没有通知同房间的其他用户
        self.active.pop(user_id, None)
        for room, members in self.rooms.items():
            members.discard(user_id)

    async def broadcast(self, room: str, message: str):
        members = self.rooms.get(room, set())
        for uid in members:
            ws = self.active.get(uid)
            if ws:
                await ws.send_text(message)
''',
        },
        "expected_functions": ["disconnect"],
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
        "expected_files": ["src/utils/date_utils.py"],
        "file_contents": {
            "src/utils/date_utils.py": '''from datetime import datetime

def parse_date(date_str: str) -> datetime:
    # BUG: 没有处理时区信息，naive datetime
    return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")

def format_date(dt: datetime, fmt: str = "%Y-%m-%d") -> str:
    return dt.strftime(fmt)

def days_between(start: str, end: str) -> int:
    d1 = parse_date(start)
    d2 = parse_date(end)
    return (d2 - d1).days
''',
        },
        "expected_functions": ["parse_date"],
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
        "expected_files": ["src/inventory/stock.py", "src/orders/service.py"],
        "file_contents": {
            "src/inventory/stock.py": '''class StockManager:
    def __init__(self, db):
        self.db = db

    def check_stock(self, product_id: int) -> int:
        row = self.db.query("SELECT quantity FROM stock WHERE product_id = ?", product_id)
        return row["quantity"] if row else 0

    def deduct_stock(self, product_id: int, amount: int) -> bool:
        # BUG: 没有使用数据库锁，并发时会超卖
        current = self.check_stock(product_id)
        if current >= amount:
            self.db.execute(
                "UPDATE stock SET quantity = quantity - ? WHERE product_id = ?",
                amount, product_id
            )
            return True
        return False
''',
        },
        "expected_functions": ["deduct_stock"],
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
        "expected_files": ["src/config/loader.py", "src/config/parser.py"],
        "file_contents": {
            "src/config/loader.py": '''import os
import re
import yaml

def load_config(path: str) -> dict:
    with open(path, "r") as f:
        raw = f.read()
    # 替换 ${VAR} 格式的环境变量
    config = yaml.safe_load(raw)
    return _resolve_env(config)

def _resolve_env(obj):
    if isinstance(obj, str):
        # BUG: 正则只匹配了 $VAR 而不是 ${VAR}
        pattern = r"\\$([A-Z_]+)"
        def replacer(m):
            return os.environ.get(m.group(1), m.group(0))
        return re.sub(pattern, replacer, obj)
    elif isinstance(obj, dict):
        return {k: _resolve_env(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env(i) for i in obj]
    return obj
''',
        },
        "expected_functions": ["_resolve_env"],
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
        "expected_files": ["src/notifications/email_sender.py"],
        "file_contents": {
            "src/notifications/email_sender.py": '''import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase

class EmailSender:
    def __init__(self, smtp_host, smtp_port, username, password):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password

    def send(self, to: str, subject: str, body: str, attachments=None):
        msg = MIMEMultipart()
        msg["To"] = to
        msg["Subject"] = subject

        if attachments:
            for filepath in attachments:
                # BUG: 没有检查文件大小，大附件导致 SMTP 超时但没有抛异常
                part = MIMEBase("application", "octet-stream")
                with open(filepath, "rb") as f:
                    part.set_payload(f.read())
                msg.attach(part)

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.login(self.username, self.password)
                server.send_message(msg)
        except Exception:
            pass  # BUG: 静默吞掉异常
''',
        },
        "expected_functions": ["send"],
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
        "expected_files": ["src/export/csv_exporter.py"],
        "file_contents": {
            "src/export/csv_exporter.py": '''import csv
import io

def export_csv(data: list[dict], filename: str) -> bytes:
    if not data:
        return b""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)

    # BUG: 编码用了 ascii 而不是 utf-8-sig（Excel 需要 BOM）
    return output.getvalue().encode("ascii", errors="replace")

def export_csv_file(data: list[dict], filepath: str):
    content = export_csv(data, filepath)
    with open(filepath, "wb") as f:
        f.write(content)
''',
        },
        "expected_functions": ["export_csv"],
    },
]


def run_validation(model_path: str = None, ollama_url: str = "http://localhost:11434",
                   ollama_model: str = "qwen3-8b"):
    """Run V3 Locator accuracy validation."""
    from offgrid.llm.llama_backend import LLMBackend
    from offgrid.experts.locator import LocatorExpert
    from offgrid.tools.executor import ToolExecutor
    from offgrid.core.context import TaskContext

    print("=" * 60)
    print("V3 验证：Locator 定位精度")
    print("=" * 60)
    print(f"模型: {model_path or ollama_model}")
    print(f"测试用例: {len(TEST_CASES)} 个")
    print()

    llm = LLMBackend(
        model_path=model_path,
        ollama_url=ollama_url,
        ollama_model=ollama_model,
    )

    file_correct = 0
    func_correct = 0
    total = len(TEST_CASES)
    details = []

    for case in TEST_CASES:
        print(f"  [Case {case['id']:2d}] {case['description'][:50]}...")

        # Create temp project structure
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_project(tmpdir, case)

            tools = ToolExecutor(project_root=tmpdir)
            locator = LocatorExpert(llm=llm, tool_executor=tools)

            ctx = TaskContext(
                user_input=case["description"],
                project_root=tmpdir,
            )

            start = time.time()
            result = locator.run(ctx)
            elapsed = time.time() - start

            if result:
                found_files = result.get("relevant_files", [])
                found_funcs = result.get("relevant_functions", [])

                # Normalize paths for comparison
                found_files_norm = [f.replace("\\", "/").lstrip("./") for f in found_files]
                expected_files_norm = [f.replace("\\", "/") for f in case["expected_files"]]

                # File-level: any expected file found?
                file_hit = any(
                    any(exp in ff or ff.endswith(exp) for ff in found_files_norm)
                    for exp in expected_files_norm
                )
                if file_hit:
                    file_correct += 1

                # Function-level: any expected function found?
                func_hit = any(
                    ef in found_funcs
                    for ef in case["expected_functions"]
                )
                if func_hit:
                    func_correct += 1

                f_status = "✅" if file_hit else "❌"
                fn_status = "✅" if func_hit else "❌"
                print(f"    文件{f_status} 函数{fn_status} | 找到: {found_files_norm[:3]} / {found_funcs[:3]} | {elapsed:.1f}s")

                details.append({
                    "case_id": case["id"],
                    "file_hit": file_hit,
                    "func_hit": func_hit,
                    "found_files": found_files_norm[:5],
                    "found_funcs": found_funcs[:5],
                    "expected_files": expected_files_norm,
                    "expected_funcs": case["expected_functions"],
                    "elapsed_s": round(elapsed, 1),
                })
            else:
                print(f"    ❌ Locator 返回 None | {elapsed:.1f}s")
                details.append({
                    "case_id": case["id"],
                    "file_hit": False,
                    "func_hit": False,
                    "error": "Locator returned None",
                })

    # ── Results ──
    file_rate = (file_correct / total * 100) if total > 0 else 0
    func_rate = (func_correct / total * 100) if total > 0 else 0

    print()
    print("=" * 60)
    print("验证结论")
    print("=" * 60)
    print(f"  文件级准确率:  {file_correct}/{total} = {file_rate:.0f}%  {'✅ PASS' if file_rate >= 60 else '❌ FAIL (触发FLEX-2)'}")
    print(f"  函数级准确率:  {func_correct}/{total} = {func_rate:.0f}%")
    print()

    if file_rate < 60:
        print("  ⚠️  文件级准确率不达标，触发 FLEX-2：")
        print("     Locator 退到两层定位（文件→函数），不做行级定位")
    if func_rate < 60:
        print("  ⚠️  函数级准确率偏低，建议增加 AST 辅助定位")

    conclusion = {
        "file_accuracy": round(file_rate, 1),
        "func_accuracy": round(func_rate, 1),
        "trigger_flex2": file_rate < 60,
        "total_cases": total,
        "details": details,
    }

    conclusion_path = os.path.join(os.path.dirname(__file__), "v3_conclusion.json")
    with open(conclusion_path, "w", encoding="utf-8") as f:
        json.dump(conclusion, f, indent=2, ensure_ascii=False)
    print(f"\n  结论已保存到: {conclusion_path}")

    return conclusion


def _create_project(tmpdir: str, case: dict):
    """Create a temporary project structure for testing."""
    # Create directories from file tree
    for line in case["file_tree"].strip().split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Remove tree characters
        name = stripped.lstrip("├─└│ ")
        if name.endswith("/"):
            os.makedirs(os.path.join(tmpdir, name.rstrip("/")), exist_ok=True)
        else:
            # It's a file, create parent dir and empty file
            # Try to reconstruct path from indentation
            pass

    # Create files with content
    for fpath, content in case.get("file_contents", {}).items():
        full_path = os.path.join(tmpdir, fpath)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

    # Create empty files for the tree structure
    _create_tree_files(tmpdir, case["file_tree"])


def _create_tree_files(tmpdir: str, tree_text: str):
    """Parse indented file tree and create actual files/dirs."""
    lines = tree_text.strip().split("\n")
    path_stack = []

    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            continue

        # Calculate depth from indentation (2 spaces per level)
        indent = len(stripped) - len(stripped.lstrip())
        depth = indent // 2
        name = stripped.strip().rstrip("/")

        # Adjust path stack to current depth
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


def main():
    parser = argparse.ArgumentParser(description="V3 Locator定位精度验证")
    parser.add_argument("--model-path", type=str, default=None, help="本地GGUF模型路径")
    parser.add_argument("--ollama-url", type=str, default="http://localhost:11434")
    parser.add_argument("--ollama-model", type=str, default="qwen3-8b")
    args = parser.parse_args()

    run_validation(
        model_path=args.model_path,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
    )


if __name__ == "__main__":
    main()
