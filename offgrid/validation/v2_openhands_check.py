"""
V2 验证：OpenHands 库集成可行性测试。
目标：确认 OpenHands 工具执行层能否作为库 import，不强制启动 HTTP 服务。
结论：决定 tools/executor.py 的实现方式（OpenHands 集成 vs 自实现）。

用法：
  python -m offgrid.validation.v2_openhands_check
"""

import json
import os
import sys
import tempfile


def run_validation():
    """Run V2 OpenHands integration validation."""
    print("=" * 60)
    print("V2 验证：OpenHands 库集成可行性")
    print("=" * 60)
    print()

    results = {
        "import_success": False,
        "extra_process_spawned": False,
        "basic_tools_work": False,
        "trigger_flex1": True,  # Default: assume we need self-implementation
        "details": [],
    }

    # ── Test 1: Import ──
    print("  [1/3] 尝试 import OpenHands 工具层...")
    try:
        from openhands.runtime.impl.local.local_runtime import LocalRuntime
        from openhands.core.config import AppConfig
        results["import_success"] = True
        results["details"].append("✅ openhands import 成功")
        print("    ✅ import 成功")
    except ImportError as e:
        results["details"].append(f"❌ import 失败: {e}")
        print(f"    ❌ import 失败: {e}")
        print("    → 触发 FLEX-1：使用自实现工具执行层")
        _write_conclusion(results)
        return results
    except Exception as e:
        results["details"].append(f"❌ import 异常: {e}")
        print(f"    ❌ import 异常: {e}")
        _write_conclusion(results)
        return results

    # ── Test 2: Execute basic tool ──
    print("  [2/3] 尝试执行基础工具 (read_file)...")
    try:
        # Create a temp file to read
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("offgrid_v2_test_content")
            test_file = f.name

        config = AppConfig()
        runtime = LocalRuntime(config)

        # Try to use the runtime to read a file
        from openhands.events.action import FileReadAction
        action = FileReadAction(path=test_file)
        obs = runtime.run_action(action)

        if hasattr(obs, "content") and "offgrid_v2_test_content" in str(obs.content):
            results["basic_tools_work"] = True
            results["details"].append("✅ read_file 执行成功")
            print("    ✅ read_file 执行成功")
        else:
            results["details"].append(f"⚠️ read_file 返回异常: {obs}")
            print(f"    ⚠️ read_file 返回异常: {obs}")

        os.unlink(test_file)
    except Exception as e:
        results["details"].append(f"❌ 工具执行失败: {e}")
        print(f"    ❌ 工具执行失败: {e}")

    # ── Test 3: Check for extra processes ──
    print("  [3/3] 检查是否启动了额外进程...")
    try:
        import psutil
        current_pid = os.getpid()
        extra_procs = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmdline = " ".join(proc.info.get("cmdline") or []).lower()
                if "openhands" in cmdline and proc.pid != current_pid:
                    extra_procs.append(f"PID={proc.pid} CMD={cmdline[:80]}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if extra_procs:
            results["extra_process_spawned"] = True
            results["details"].append(f"⚠️ 检测到额外进程: {extra_procs}")
            print(f"    ⚠️ 检测到额外进程: {extra_procs}")
        else:
            results["details"].append("✅ 无额外进程启动")
            print("    ✅ 无额外进程启动")
    except ImportError:
        results["details"].append("⚠️ psutil 未安装，跳过进程检查")
        print("    ⚠️ psutil 未安装，跳过进程检查")

    # ── Conclusion ──
    if results["import_success"] and results["basic_tools_work"] and not results["extra_process_spawned"]:
        results["trigger_flex1"] = False
        print("\n  ✅ 结论：OpenHands 可作为库集成")
    else:
        results["trigger_flex1"] = True
        print("\n  ⚠️ 结论：触发 FLEX-1，使用自实现工具执行层")

    _write_conclusion(results)
    return results


def _write_conclusion(results: dict):
    """Write conclusion to JSON file."""
    conclusion_path = os.path.join(os.path.dirname(__file__), "v2_conclusion.json")
    with open(conclusion_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  结论已保存到: {conclusion_path}")


def main():
    run_validation()


if __name__ == "__main__":
    main()
