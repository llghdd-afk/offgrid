"""
PROJECT.md memory: project structure info (language, framework, test command, etc).
Spec §7.2: split from KAIWU.md into .offgrid/PROJECT.md.
"""

import logging
import os
import re
from typing import Optional

from offgrid.core.context import TaskContext

logger = logging.getLogger(__name__)

PROJECT_MD_TEMPLATE = """# Kaiwu 项目记忆
> 自动维护，请勿手动删除关键字段

## 基础信息
- 语言：{language}
- 框架：{framework}
- 包管理：{pkg_manager}
- 测试命令：{test_cmd}
- 主入口：{entry_point}
- 代码风格：{code_style}

## 已知结构规律

## 注意事项
"""

# Token limits (approximate char counts)
GATE_LIMIT = 500       # 10% of model window
LOCATOR_LIMIT = 750    # 15%
VERIFIER_LIMIT = 250   # 5%


def _offgrid_dir(project_root: str) -> str:
    return os.path.join(project_root, ".offgrid")


def _md_path(project_root: str) -> str:
    return os.path.join(_offgrid_dir(project_root), "PROJECT.md")


def _ensure_dir(project_root: str):
    d = _offgrid_dir(project_root)
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _extract_section(content: str, header: str) -> str:
    """Extract content between a ## header and the next ## header."""
    pattern = re.escape(header) + r"\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _replace_section(content: str, header: str, new_body: str) -> str:
    """Replace the body of a ## section, preserving the header."""
    pattern = re.escape(header) + r"\n(.*?)(?=\n## |\Z)"
    replacement = header + "\n" + new_body + "\n"
    new_content, count = re.subn(pattern, replacement, content, count=1, flags=re.DOTALL)
    if count == 0:
        # Section not found, append
        new_content = content.rstrip() + "\n\n" + replacement
    return new_content


# ── Detection helpers (reused from offgrid_md.py) ──


def _detect_language(project_root: str) -> str:
    ext_count: dict[str, int] = {}
    try:
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", "venv", ".venv")]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in (".py", ".js", ".ts", ".go", ".rs", ".java", ".cpp", ".c"):
                    ext_count[ext] = ext_count.get(ext, 0) + 1
    except Exception:
        pass
    if not ext_count:
        return "未检测"
    top_ext = max(ext_count, key=ext_count.get)
    lang_map = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".go": "Go", ".rs": "Rust", ".java": "Java", ".cpp": "C++", ".c": "C",
    }
    return lang_map.get(top_ext, "未检测")


def _detect_framework(project_root: str) -> str:
    indicators = {
        "requirements.txt": {"fastapi": "FastAPI", "django": "Django", "flask": "Flask"},
        "pyproject.toml": {"fastapi": "FastAPI", "django": "Django", "flask": "Flask"},
        "package.json": {"react": "React", "vue": "Vue", "next": "Next.js", "express": "Express"},
        "go.mod": {"gin": "Gin", "echo": "Echo", "fiber": "Fiber"},
    }
    for dep_file, frameworks in indicators.items():
        fpath = os.path.join(project_root, dep_file)
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read().lower()
                for keyword, name in frameworks.items():
                    if keyword in content:
                        return name
            except Exception:
                pass
    return "未检测"


def _detect_test_cmd(project_root: str) -> str:
    if os.path.exists(os.path.join(project_root, "pytest.ini")) or \
       os.path.exists(os.path.join(project_root, "pyproject.toml")):
        return "pytest"
    if os.path.exists(os.path.join(project_root, "package.json")):
        return "npm test"
    if os.path.exists(os.path.join(project_root, "go.mod")):
        return "go test ./..."
    return "未检测"


def _detect_entry(project_root: str) -> str:
    candidates = ["main.py", "app.py", "src/main.py", "src/app.py", "index.js", "index.ts", "main.go", "cmd/main.go"]
    for c in candidates:
        if os.path.exists(os.path.join(project_root, c)):
            return c
    return "未检测"


def _detect_pkg_manager(project_root: str) -> str:
    checks = [
        ("poetry.lock", "Poetry"),
        ("Pipfile.lock", "Pipenv"),
        ("pdm.lock", "PDM"),
        ("requirements.txt", "pip"),
        ("yarn.lock", "Yarn"),
        ("pnpm-lock.yaml", "pnpm"),
        ("package-lock.json", "npm"),
        ("go.sum", "Go Modules"),
        ("Cargo.lock", "Cargo"),
    ]
    for filename, manager in checks:
        if os.path.exists(os.path.join(project_root, filename)):
            return manager
    # Fallback: check pyproject.toml for build system
    pyproject = os.path.join(project_root, "pyproject.toml")
    if os.path.exists(pyproject):
        try:
            with open(pyproject, "r", encoding="utf-8") as f:
                content = f.read().lower()
            if "poetry" in content:
                return "Poetry"
            if "pdm" in content:
                return "PDM"
            return "pip"
        except Exception:
            pass
    return "未检测"


def _detect_code_style(project_root: str) -> str:
    style_files = {
        ".flake8": "Flake8",
        "setup.cfg": "Flake8",
        ".pylintrc": "Pylint",
        "ruff.toml": "Ruff",
        ".eslintrc.js": "ESLint",
        ".eslintrc.json": "ESLint",
        ".prettierrc": "Prettier",
        "biome.json": "Biome",
    }
    for filename, style in style_files.items():
        if os.path.exists(os.path.join(project_root, filename)):
            return style
    # Check pyproject.toml for tool sections
    pyproject = os.path.join(project_root, "pyproject.toml")
    if os.path.exists(pyproject):
        try:
            with open(pyproject, "r", encoding="utf-8") as f:
                content = f.read().lower()
            if "[tool.ruff]" in content:
                return "Ruff"
            if "[tool.black]" in content:
                return "Black"
            if "[tool.flake8]" in content:
                return "Flake8"
        except Exception:
            pass
    return "未检测"


# ── Public API ──


def load(project_root: str) -> str:
    """Return full PROJECT.md content as injectable context."""
    path = _md_path(project_root)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.warning("Failed to read PROJECT.md: %s", e)
        return ""


def save(project_root: str, ctx: TaskContext):
    """Update PROJECT.md after a successful task."""
    path = _md_path(project_root)
    if not os.path.exists(path):
        # Auto-init on first save
        init(project_root)
        path = _md_path(project_root)
        if not os.path.exists(path):
            return

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.warning("Failed to read PROJECT.md for save: %s", e)
        return

    # Update 已知结构规律 from locator results
    if ctx.locator_output:
        files = ctx.locator_output.get("relevant_files", [])
        funcs = ctx.locator_output.get("relevant_functions", [])
        if files or funcs:
            existing = _extract_section(content, "## 已知结构规律")
            existing_lines = set(existing.split("\n")) if existing else set()
            new_lines = []
            for f in files[:5]:
                line = f"- {f}"
                if line not in existing_lines:
                    new_lines.append(line)
            for fn in funcs[:3]:
                line = f"- fn: {fn}"
                if line not in existing_lines:
                    new_lines.append(line)
            if new_lines:
                updated = (existing + "\n" + "\n".join(new_lines)).strip()
                # Keep section bounded
                lines = updated.split("\n")
                if len(lines) > 30:
                    lines = lines[-30:]
                content = _replace_section(content, "## 已知结构规律", "\n".join(lines))

    # Update 注意事项 from verifier results
    if ctx.verifier_output:
        notes_section = _extract_section(content, "## 注意事项")
        existing_lines = set(notes_section.split("\n")) if notes_section else set()
        new_lines = []
        if ctx.verifier_output.get("passed"):
            tests_passed = ctx.verifier_output.get("tests_passed", 0)
            tests_total = ctx.verifier_output.get("tests_total", 0)
            if tests_total > 0:
                line = f"- 测试通过 {tests_passed}/{tests_total}"
                if line not in existing_lines:
                    new_lines.append(line)
        else:
            error = ctx.verifier_output.get("error_detail", "")
            if error:
                line = f"- 注意: {error[:80]}"
                if line not in existing_lines:
                    new_lines.append(line)
        if new_lines:
            updated = (notes_section + "\n" + "\n".join(new_lines)).strip()
            lines = updated.split("\n")
            if len(lines) > 20:
                lines = lines[-20:]
            content = _replace_section(content, "## 注意事项", "\n".join(lines))

    # Update framework detection if still 未检测
    content = _update_project_info(content, ctx)

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Saved PROJECT.md")
    except Exception as e:
        logger.warning("Failed to write PROJECT.md: %s", e)


def init(project_root: str) -> str:
    """Auto-detect project info and create PROJECT.md."""
    _ensure_dir(project_root)
    path = _md_path(project_root)
    if os.path.exists(path):
        return f"PROJECT.md already exists at {path}"

    content = PROJECT_MD_TEMPLATE.format(
        language=_detect_language(project_root),
        framework=_detect_framework(project_root),
        pkg_manager=_detect_pkg_manager(project_root),
        test_cmd=_detect_test_cmd(project_root),
        entry_point=_detect_entry(project_root),
        code_style=_detect_code_style(project_root),
    )

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Created PROJECT.md at {path}"
    except Exception as e:
        return f"Failed to create PROJECT.md: {e}"


def show(project_root: str) -> str:
    """Display PROJECT.md content."""
    path = _md_path(project_root)
    if not os.path.exists(path):
        return "PROJECT.md not found. Run `offgrid init` to create."
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Failed to read PROJECT.md: {e}"


def load_for_gate(project_root: str) -> str:
    """Return 基础信息 section only (token limit ~500 chars)."""
    content = load(project_root)
    if not content:
        return ""
    section = _extract_section(content, "## 基础信息")
    if not section:
        return ""
    result = f"项目信息：\n{section}\n"
    if len(result) > GATE_LIMIT:
        result = result[:GATE_LIMIT] + "\n...(截断)"
    return result


def load_for_locator(project_root: str) -> str:
    """Return 已知结构规律 section (token limit ~750 chars)."""
    content = load(project_root)
    if not content:
        return ""
    section = _extract_section(content, "## 已知结构规律")
    if not section:
        return ""
    result = f"已知结构规律：\n{section}\n"
    if len(result) > LOCATOR_LIMIT:
        result = result[:LOCATOR_LIMIT] + "\n...(截断)"
    return result


def load_for_verifier(project_root: str) -> str:
    """Return 注意事项 section (token limit ~250 chars)."""
    content = load(project_root)
    if not content:
        return ""
    section = _extract_section(content, "## 注意事项")
    if not section:
        return ""
    result = f"注意事项：\n{section}\n"
    if len(result) > VERIFIER_LIMIT:
        result = result[:VERIFIER_LIMIT] + "\n...(截断)"
    return result


def _update_project_info(content: str, ctx: TaskContext) -> str:
    """Update project info if we detected new info from task files."""
    files = []
    if ctx.locator_output:
        files = ctx.locator_output.get("relevant_files", [])
    for f in files:
        fl = f.lower()
        if ("fastapi" in fl or "app.py" in fl) and "框架：未检测" in content:
            content = content.replace("框架：未检测", "框架：FastAPI")
        elif ("django" in fl or "manage.py" in fl) and "框架：未检测" in content:
            content = content.replace("框架：未检测", "框架：Django")
        elif "flask" in fl and "框架：未检测" in content:
            content = content.replace("框架：未检测", "框架：Flask")
    return content
