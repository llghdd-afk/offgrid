"""
OFFGRID.md project rules loader.
Loads user-defined rules from OFFGRID.md, parses by section tags,
injects relevant sections into expert prompts.
P1-RED-1: Injected tokens must not exceed 15% of model context window.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Supported section tags
_SECTION_KEYS = ("all", "bugfix", "codegen", "test", "refactor", "doc", "office")

# Map expert_type to section key
_TYPE_TO_SECTION = {
    "locator_repair": "bugfix",
    "codegen": "codegen",
    "refactor": "refactor",
    "doc": "doc",
    "test": "test",
    "office": "office",
}


def load_offgrid_md(project_root: str) -> dict[str, str]:
    """
    Load OFFGRID.md, parse by [section] tags.
    Returns {"all": "...", "bugfix": "...", ...}.
    Falls back to ~/.offgrid/OFFGRID.md if not found in project root.
    Returns empty dict if no file found (silent).
    """
    path = Path(project_root) / "OFFGRID.md"
    if not path.exists():
        path = Path.home() / ".offgrid" / "OFFGRID.md"
        if not path.exists():
            return {}

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.debug("[offgrid_md] Failed to read %s: %s", path, e)
        return {}

    sections: dict[str, list[str]] = {k: [] for k in _SECTION_KEYS}
    current = "all"

    for line in content.splitlines():
        stripped = line.strip()
        # Detect section tag: ## [bugfix] or ## [all]
        matched = False
        for key in _SECTION_KEYS:
            if stripped.startswith(f"## [{key}]"):
                current = key
                matched = True
                break
        if not matched:
            # Skip the file title line
            if not stripped.startswith("# OFFGRID.md"):
                sections[current].append(line)

    return {k: "\n".join(v).strip() for k, v in sections.items() if v and "\n".join(v).strip()}


def build_offgrid_system(expert_type: str, offgrid_sections: dict[str, str]) -> str:
    """
    Build system prompt injection from OFFGRID.md sections.
    Always injects [all], plus the section matching expert_type.
    P1-RED-1: Total tokens capped at ~15% of 8K window (1200 tokens ≈ 4800 chars).
    """
    if not offgrid_sections:
        return ""

    parts = []

    # Always inject [all]
    if "all" in offgrid_sections:
        parts.append(f"## 项目规则\n{offgrid_sections['all']}")

    # Inject task-type-specific section
    section_key = _TYPE_TO_SECTION.get(expert_type)
    if section_key and section_key in offgrid_sections:
        parts.append(f"## {expert_type}规则\n{offgrid_sections[section_key]}")

    if not parts:
        return ""

    injected = "\n\n".join(parts)

    # P1-RED-1: token cap (rough estimate: 1 token ≈ 4 chars)
    MAX_CHARS = 4800  # ~1200 tokens, 15% of 8K
    if len(injected) > MAX_CHARS:
        injected = injected[:MAX_CHARS] + "\n...(已截断)"

    return injected


def generate_offgrid_template(project_root: str) -> str:
    """
    Generate OFFGRID.md template in project root.
    Auto-detects test framework. Returns status message.
    """
    offgrid_path = Path(project_root) / "OFFGRID.md"
    if offgrid_path.exists():
        return "OFFGRID.md已存在，跳过"

    # Auto-detect test command
    test_cmd = "pytest tests/ -v"
    if (Path(project_root) / "package.json").exists():
        test_cmd = "npm test"
    elif (Path(project_root) / "go.mod").exists():
        test_cmd = "go test ./..."
    elif (Path(project_root) / "Cargo.toml").exists():
        test_cmd = "cargo test"

    template = f"""# OFFGRID.md
# 项目规则文件，OffGrid启动时自动加载
# 编辑此文件来告诉OffGrid你的项目规范

## [all] 通用规则
- 运行测试：{test_cmd}
- 在这里写你的项目约定，比如：
- 认证逻辑在：src/auth/
- 数据库操作在：src/db/

## [bugfix] Bug修复规则
- 修复前先理解错误原因

## [codegen] 代码生成规则
- 在这里写新代码的规范

## [test] 测试规则
- 使用pytest

## [refactor] 重构规则
- 每次只做一种重构
"""
    try:
        offgrid_path.write_text(template, encoding="utf-8")
        return f"[green]✓[/green] 已生成 OFFGRID.md，请编辑填写你的项目规范"
    except Exception as e:
        return f"[red]生成失败：{e}[/red]"
