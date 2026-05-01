"""
V6 验证：LLM 从轨迹生成专家 YAML 的质量测试。
目标：验证 ExpertGeneratorFlywheel 能从相似任务轨迹中提取有效专家定义。
验收标准：
  - 生成的专家 YAML 结构完整（name, trigger_keywords, system_prompt, pipeline）
  - trigger_keywords 能覆盖原始任务描述中的关键词
  - pipeline 步骤合法（locator/generator/verifier）
  - system_prompt 非空且包含领域知识

注意：需要 Ollama 在线才能运行 LLM 生成。

用法：
  python -m offgrid.validation.v6_expert_generation --ollama-model gemma3:4b
"""

import argparse
import io
import json
import os
import sys
import time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from offgrid.flywheel.trajectory_collector import TaskTrajectory

# ── 3 组 × 5 条合成轨迹 ──────────────────────────────────────

TRAJECTORY_GROUPS = {
    "fastapi_crud": {
        "label": "FastAPI CRUD endpoint",
        "expected_keywords": ["fastapi", "crud", "endpoint", "api", "pydantic"],
        "trajectories": [
            TaskTrajectory(
                task_id="fa-001", user_input="帮我写一个FastAPI的用户CRUD接口",
                gate_result={"expert_type": "codegen", "task_summary": "FastAPI user CRUD"},
                expert_used="codegen", pipeline_steps=["generator", "verifier"],
                files_modified=["src/api/users.py", "src/models/user.py"],
                success=True, latency_s=12.3, model_used="gemma3:4b",
                timestamp="2026-04-26T10:00:00Z", search_triggered=False, project_hash="abc123",
            ),
            TaskTrajectory(
                task_id="fa-002", user_input="用FastAPI实现商品列表的增删改查",
                gate_result={"expert_type": "codegen", "task_summary": "FastAPI product CRUD"},
                expert_used="codegen", pipeline_steps=["generator", "verifier"],
                files_modified=["src/api/products.py", "src/schemas/product.py"],
                success=True, latency_s=14.1, model_used="gemma3:4b",
                timestamp="2026-04-26T10:05:00Z", search_triggered=False, project_hash="abc123",
            ),
            TaskTrajectory(
                task_id="fa-003", user_input="FastAPI订单接口，包含创建、查询、更新状态",
                gate_result={"expert_type": "codegen", "task_summary": "FastAPI order endpoints"},
                expert_used="codegen", pipeline_steps=["generator", "verifier"],
                files_modified=["src/api/orders.py"],
                success=True, latency_s=11.8, model_used="gemma3:4b",
                timestamp="2026-04-26T10:10:00Z", search_triggered=False, project_hash="abc123",
            ),
            TaskTrajectory(
                task_id="fa-004", user_input="写一个FastAPI的分类管理接口，支持树形结构",
                gate_result={"expert_type": "codegen", "task_summary": "FastAPI category tree CRUD"},
                expert_used="codegen", pipeline_steps=["generator", "verifier"],
                files_modified=["src/api/categories.py", "src/models/category.py"],
                success=True, latency_s=15.2, model_used="gemma3:4b",
                timestamp="2026-04-26T10:15:00Z", search_triggered=False, project_hash="abc123",
            ),
            TaskTrajectory(
                task_id="fa-005", user_input="FastAPI实现标签的CRUD，带分页和搜索",
                gate_result={"expert_type": "codegen", "task_summary": "FastAPI tag CRUD with pagination"},
                expert_used="codegen", pipeline_steps=["generator", "verifier"],
                files_modified=["src/api/tags.py"],
                success=True, latency_s=13.0, model_used="gemma3:4b",
                timestamp="2026-04-26T10:20:00Z", search_triggered=False, project_hash="abc123",
            ),
        ],
    },
    "pytest_fixture": {
        "label": "pytest fixture",
        "expected_keywords": ["pytest", "fixture", "test", "mock", "conftest"],
        "trajectories": [
            TaskTrajectory(
                task_id="pt-001", user_input="帮我写一个pytest的数据库fixture，每个测试自动回滚",
                gate_result={"expert_type": "codegen", "task_summary": "pytest db fixture with rollback"},
                expert_used="codegen", pipeline_steps=["generator", "verifier"],
                files_modified=["tests/conftest.py"],
                success=True, latency_s=8.5, model_used="gemma3:4b",
                timestamp="2026-04-26T11:00:00Z", search_triggered=False, project_hash="def456",
            ),
            TaskTrajectory(
                task_id="pt-002", user_input="写pytest fixture mock掉外部HTTP请求",
                gate_result={"expert_type": "codegen", "task_summary": "pytest fixture mock HTTP"},
                expert_used="codegen", pipeline_steps=["generator", "verifier"],
                files_modified=["tests/conftest.py", "tests/fixtures/http_mock.py"],
                success=True, latency_s=9.2, model_used="gemma3:4b",
                timestamp="2026-04-26T11:05:00Z", search_triggered=False, project_hash="def456",
            ),
            TaskTrajectory(
                task_id="pt-003", user_input="pytest conftest里加一个Redis fixture，用fakeredis",
                gate_result={"expert_type": "codegen", "task_summary": "pytest Redis fixture"},
                expert_used="codegen", pipeline_steps=["generator", "verifier"],
                files_modified=["tests/conftest.py"],
                success=True, latency_s=7.8, model_used="gemma3:4b",
                timestamp="2026-04-26T11:10:00Z", search_triggered=False, project_hash="def456",
            ),
            TaskTrajectory(
                task_id="pt-004", user_input="写一个pytest fixture提供临时文件目录，测试后自动清理",
                gate_result={"expert_type": "codegen", "task_summary": "pytest tmpdir fixture"},
                expert_used="codegen", pipeline_steps=["generator", "verifier"],
                files_modified=["tests/conftest.py"],
                success=True, latency_s=6.9, model_used="gemma3:4b",
                timestamp="2026-04-26T11:15:00Z", search_triggered=False, project_hash="def456",
            ),
            TaskTrajectory(
                task_id="pt-005", user_input="pytest fixture实现用户认证token，parametrize不同角色",
                gate_result={"expert_type": "codegen", "task_summary": "pytest auth fixture parametrize"},
                expert_used="codegen", pipeline_steps=["generator", "verifier"],
                files_modified=["tests/conftest.py", "tests/fixtures/auth.py"],
                success=True, latency_s=10.1, model_used="gemma3:4b",
                timestamp="2026-04-26T11:20:00Z", search_triggered=False, project_hash="def456",
            ),
        ],
    },
    "db_migration": {
        "label": "database migration",
        "expected_keywords": ["migration", "alembic", "database", "schema", "migrate"],
        "trajectories": [
            TaskTrajectory(
                task_id="db-001", user_input="帮我写一个Alembic迁移脚本，给users表加email字段",
                gate_result={"expert_type": "codegen", "task_summary": "Alembic migration add email column"},
                expert_used="codegen", pipeline_steps=["generator", "verifier"],
                files_modified=["alembic/versions/001_add_email.py"],
                success=True, latency_s=9.0, model_used="gemma3:4b",
                timestamp="2026-04-26T12:00:00Z", search_triggered=False, project_hash="ghi789",
            ),
            TaskTrajectory(
                task_id="db-002", user_input="写数据库迁移：创建orders表，包含外键关联users",
                gate_result={"expert_type": "codegen", "task_summary": "migration create orders table"},
                expert_used="codegen", pipeline_steps=["generator", "verifier"],
                files_modified=["alembic/versions/002_create_orders.py", "src/models/order.py"],
                success=True, latency_s=11.5, model_used="gemma3:4b",
                timestamp="2026-04-26T12:05:00Z", search_triggered=False, project_hash="ghi789",
            ),
            TaskTrajectory(
                task_id="db-003", user_input="Alembic迁移：给products表加索引和唯一约束",
                gate_result={"expert_type": "codegen", "task_summary": "Alembic add index and unique constraint"},
                expert_used="codegen", pipeline_steps=["generator", "verifier"],
                files_modified=["alembic/versions/003_add_product_index.py"],
                success=True, latency_s=8.3, model_used="gemma3:4b",
                timestamp="2026-04-26T12:10:00Z", search_triggered=False, project_hash="ghi789",
            ),
            TaskTrajectory(
                task_id="db-004", user_input="写迁移脚本把status字段从字符串改成枚举类型",
                gate_result={"expert_type": "codegen", "task_summary": "migration change column type to enum"},
                expert_used="codegen", pipeline_steps=["generator", "verifier"],
                files_modified=["alembic/versions/004_status_enum.py"],
                success=True, latency_s=10.7, model_used="gemma3:4b",
                timestamp="2026-04-26T12:15:00Z", search_triggered=False, project_hash="ghi789",
            ),
            TaskTrajectory(
                task_id="db-005", user_input="数据库迁移：拆分address字段为province/city/district",
                gate_result={"expert_type": "codegen", "task_summary": "migration split address column"},
                expert_used="codegen", pipeline_steps=["generator", "verifier"],
                files_modified=["alembic/versions/005_split_address.py", "src/models/user.py"],
                success=True, latency_s=12.0, model_used="gemma3:4b",
                timestamp="2026-04-26T12:20:00Z", search_triggered=False, project_hash="ghi789",
            ),
        ],
    },
}


def _check_keyword_coverage(expert: dict, group_info: dict) -> dict:
    """Check if generated expert's keywords cover the expected domain."""
    generated_kws = [kw.lower() for kw in expert.get("trigger_keywords", [])]
    expected_kws = [kw.lower() for kw in group_info["expected_keywords"]]

    # Check: any expected keyword appears in generated keywords?
    hits = [ek for ek in expected_kws if any(ek in gk or gk in ek for gk in generated_kws)]

    # Check: do generated keywords match original task descriptions?
    all_inputs = " ".join(t.user_input.lower() for t in group_info["trajectories"])
    input_hits = [gk for gk in generated_kws if gk in all_inputs]

    return {
        "expected_keyword_coverage": len(hits) / len(expected_kws) if expected_kws else 0,
        "expected_hits": hits,
        "input_keyword_hits": input_hits,
        "generated_keywords": generated_kws,
    }


def _validate_expert_structure(expert: dict) -> dict:
    """Validate the generated expert has all required fields and valid values."""
    checks = {}

    # Required fields
    required = ["name", "trigger_keywords", "system_prompt", "pipeline"]
    for field in required:
        checks[f"has_{field}"] = field in expert and bool(expert[field])

    # Pipeline validity
    valid_steps = {"locator", "generator", "verifier"}
    pipeline = expert.get("pipeline", [])
    checks["pipeline_valid"] = all(s in valid_steps for s in pipeline) and len(pipeline) > 0

    # System prompt quality
    sp = expert.get("system_prompt", "")
    checks["system_prompt_nonempty"] = len(sp) > 20
    checks["system_prompt_has_content"] = any(
        kw in sp.lower() for kw in ["专家", "expert", "你是", "you are", "专注", "focus"]
    )

    # Trigger confidence
    conf = expert.get("trigger_min_confidence", 0)
    checks["confidence_reasonable"] = 0.5 <= conf <= 1.0

    checks["all_passed"] = all(checks.values())
    return checks


def run_validation(ollama_model: str = "gemma3:4b"):
    from offgrid.llm.llama_backend import LLMBackend
    from offgrid.flywheel.expert_generator import ExpertGeneratorFlywheel

    print("=" * 60)
    print("V6 验证：LLM 专家生成质量")
    print("=" * 60)
    print(f"模型: {ollama_model}")
    print(f"测试组: {len(TRAJECTORY_GROUPS)} 组 x 5 条轨迹")
    print()

    # Check Ollama availability
    ollama_available = True
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        if resp.status_code != 200:
            ollama_available = False
    except Exception:
        ollama_available = False

    if not ollama_available:
        print("  Ollama 不在线，无法运行 LLM 生成。")
        print("  请启动 Ollama 后重试: ollama serve")
        conclusion = {
            "status": "skipped",
            "reason": "Ollama offline",
            "groups": {},
        }
        _save_conclusion(conclusion)
        return conclusion

    llm = LLMBackend(ollama_model=ollama_model)
    generator = ExpertGeneratorFlywheel(llm)

    group_results = {}
    total_passed = 0
    total_groups = len(TRAJECTORY_GROUPS)

    for group_key, group_info in TRAJECTORY_GROUPS.items():
        print(f"── 组: {group_info['label']} ──")

        # Build pattern dict matching PatternDetector output format
        pattern = {
            "expert_type": "codegen",
            "count": len(group_info["trajectories"]),
            "trajectories": group_info["trajectories"],
            "pipeline": group_info["trajectories"][0].pipeline_steps,
        }

        t0 = time.time()
        expert = generator.generate(pattern)
        elapsed = time.time() - t0

        if expert is None:
            print(f"    生成失败 (LLM返回无法解析的结果) [{elapsed:.1f}s]")
            group_results[group_key] = {
                "label": group_info["label"],
                "generated": False,
                "elapsed_s": round(elapsed, 1),
                "error": "generation returned None",
            }
            continue

        print(f"    生成成功: {expert.get('name', '?')} [{elapsed:.1f}s]")

        # Validate structure
        structure_checks = _validate_expert_structure(expert)
        print(f"    结构验证: {'PASS' if structure_checks['all_passed'] else 'FAIL'}")
        for check_name, passed in structure_checks.items():
            if check_name == "all_passed":
                continue
            status = "OK" if passed else "FAIL"
            print(f"      {check_name}: {status}")

        # Check keyword coverage
        kw_coverage = _check_keyword_coverage(expert, group_info)
        coverage_pct = kw_coverage["expected_keyword_coverage"] * 100
        print(f"    关键词覆盖: {coverage_pct:.0f}% ({kw_coverage['expected_hits']})")
        print(f"    生成的关键词: {kw_coverage['generated_keywords']}")
        print(f"    输入命中: {kw_coverage['input_keyword_hits']}")

        group_passed = structure_checks["all_passed"] and coverage_pct >= 40
        if group_passed:
            total_passed += 1
        print(f"    组判定: {'PASS' if group_passed else 'FAIL'}")
        print()

        group_results[group_key] = {
            "label": group_info["label"],
            "generated": True,
            "expert_name": expert.get("name"),
            "expert_keywords": expert.get("trigger_keywords", []),
            "expert_pipeline": expert.get("pipeline", []),
            "system_prompt_len": len(expert.get("system_prompt", "")),
            "structure_checks": structure_checks,
            "keyword_coverage": kw_coverage["expected_keyword_coverage"],
            "elapsed_s": round(elapsed, 1),
            "passed": group_passed,
        }

    # ── Summary ──
    print("=" * 60)
    print("验证结论")
    print("=" * 60)
    print(f"  通过组数: {total_passed}/{total_groups}")
    overall = total_passed >= 2  # At least 2/3 groups pass
    print(f"  总体判定: {'PASS' if overall else 'FAIL'} (需 >= 2/3 组通过)")

    if not overall:
        print("  建议: 换更大模型重试，或优化 ExpertGeneratorFlywheel 的 prompt")

    V6_CONCLUSION = {
        "status": "completed",
        "model": ollama_model,
        "groups_passed": total_passed,
        "groups_total": total_groups,
        "overall_pass": overall,
        "groups": group_results,
    }

    _save_conclusion(V6_CONCLUSION)
    return V6_CONCLUSION


def _save_conclusion(conclusion: dict):
    conclusion_path = os.path.join(os.path.dirname(__file__), "v6_conclusion.json")
    with open(conclusion_path, "w", encoding="utf-8") as f:
        json.dump(conclusion, f, indent=2, ensure_ascii=False)
    print(f"\n  结论已保存到: {conclusion_path}")


def main():
    parser = argparse.ArgumentParser(description="V6 专家生成质量验证")
    parser.add_argument("--ollama-model", type=str, default="gemma3:4b")
    args = parser.parse_args()
    run_validation(ollama_model=args.ollama_model)


if __name__ == "__main__":
    main()
