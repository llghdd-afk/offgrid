"""
V1 验证：Gate JSON 结构化输出稳定性测试。
目标：确认本地模型能可靠输出结构化 JSON 用于路由。
红线：JSON 解析成功率 < 95% 则启用 grammar 约束。

用法：
  python -m offgrid.validation.v1_gate_stability --ollama-model qwen3-8b
  python -m offgrid.validation.v1_gate_stability --model-path /path/to/model.gguf
"""

import argparse
import io
import json
import os
import sys
import time
from collections import Counter

# Fix Windows GBK encoding issue
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── 100 条测试输入（5 类各 20 条）──────────────────────────────
TEST_INPUTS = {
    "locator_repair": [
        "这个函数报错了帮我修一下",
        "登录接口返回500错误",
        "用户注册时密码校验失败",
        "数据库连接超时怎么修",
        "这个API返回的数据格式不对",
        "JWT token验证总是失败",
        "文件上传功能报错了",
        "分页查询结果不正确",
        "缓存没有正确失效",
        "并发请求时出现数据竞争",
        "单元测试跑不过帮我看看",
        "这个正则表达式匹配不对",
        "日期格式转换有bug",
        "权限校验逻辑有漏洞",
        "WebSocket连接断开后没有重连",
        "邮件发送功能失败了",
        "定时任务没有按时执行",
        "日志记录的格式不对",
        "配置文件读取报错",
        "数据导出功能生成的CSV格式有问题",
    ],
    "codegen": [
        "帮我写一个用户登录接口",
        "实现一个LRU缓存",
        "写一个文件上传的工具函数",
        "帮我补全这个排序算法",
        "生成一个数据库迁移脚本",
        "写一个JWT token生成函数",
        "实现一个简单的消息队列",
        "帮我写一个配置文件解析器",
        "生成一个REST API的CRUD接口",
        "写一个日志轮转的工具类",
        "实现一个简单的状态机",
        "帮我写一个命令行参数解析",
        "生成一个WebSocket服务端",
        "写一个数据验证的装饰器",
        "实现一个简单的插件系统",
        "帮我写一个重试机制",
        "生成一个数据库连接池",
        "写一个异步任务调度器",
        "实现一个简单的模板引擎",
        "帮我写一个HTTP客户端封装",
    ],
    "refactor": [
        "这段代码太乱了帮我整理",
        "把这个大函数拆分成小函数",
        "这个类的职责太多了需要重构",
        "帮我把回调改成async/await",
        "这段重复代码需要抽取公共方法",
        "把硬编码的配置提取到配置文件",
        "这个模块的依赖关系太复杂了",
        "帮我优化这段SQL查询",
        "把这个同步接口改成异步的",
        "这个函数的参数太多了需要简化",
        "帮我把这段代码改成更Pythonic的写法",
        "这个类的继承层次太深了",
        "把全局变量改成依赖注入",
        "这段错误处理逻辑需要统一",
        "帮我把这个单体模块拆分",
        "优化这段循环的性能",
        "把这个字典操作改成dataclass",
        "这个文件太长了帮我拆分",
        "帮我统一这个项目的命名风格",
        "把这段面条代码改成策略模式",
    ],
    "doc": [
        "帮我写注释",
        "给这个函数加docstring",
        "帮我写README",
        "生成API文档",
        "帮我写这个模块的使用说明",
        "给这个类加类型注解",
        "帮我写CHANGELOG",
        "生成这个接口的请求示例",
        "帮我写部署文档",
        "给这段代码加行内注释",
        "帮我写测试用例的说明",
        "生成配置文件的模板和说明",
        "帮我写错误码文档",
        "给这个项目写贡献指南",
        "帮我写数据库表结构文档",
        "生成这个SDK的快速开始文档",
        "帮我写版本升级指南",
        "给这个函数写使用示例",
        "帮我写安全策略文档",
        "生成这个微服务的架构说明",
    ],
    "office": [
        "帮我生成一个Excel报表",
        "把这个数据导出成Word文档",
        "帮我做一个PPT模板",
        "生成一个项目进度的甘特图",
        "帮我把CSV转成Excel并加格式",
        "生成一个数据分析报告的Word",
        "帮我做一个会议纪要模板",
        "把数据库数据导出成Excel",
        "帮我生成一个项目周报模板",
        "做一个数据可视化的Excel图表",
        "帮我把JSON数据转成Excel表格",
        "生成一个需求文档的Word模板",
        "帮我做一个测试报告的Excel",
        "把API响应数据整理成表格",
        "帮我生成一个发票模板",
        "做一个库存管理的Excel表",
        "帮我把日志数据整理成报表",
        "生成一个人员排班表",
        "帮我做一个预算表模板",
        "把监控数据导出成图表报告",
    ],
}

VALID_EXPERT_TYPES = {"locator_repair", "codegen", "refactor", "doc", "office"}
VALID_DIFFICULTIES = {"easy", "hard"}


def run_validation(model_path: str = None, ollama_url: str = "http://localhost:11434",
                   ollama_model: str = "qwen3-8b", use_grammar: bool = False):
    """Run V1 Gate stability validation."""
    from offgrid.llm.llama_backend import LLMBackend
    from offgrid.core.gate import Gate

    print("=" * 60)
    print("V1 验证：Gate JSON 结构化输出稳定性")
    print("=" * 60)
    print(f"模型: {model_path or ollama_model}")
    print(f"Grammar约束: {'启用' if use_grammar else '关闭'}")
    print()

    llm = LLMBackend(
        model_path=model_path,
        ollama_url=ollama_url,
        ollama_model=ollama_model,
    )
    gate = Gate(llm=llm, use_grammar=use_grammar)

    total = 0
    json_ok = 0
    type_correct = 0
    type_counts = Counter()
    errors = []
    latencies = []

    for expected_type, inputs in TEST_INPUTS.items():
        for user_input in inputs:
            total += 1
            start = time.time()

            try:
                result = gate.classify(user_input)
                elapsed_ms = (time.time() - start) * 1000
                latencies.append(elapsed_ms)

                # Check JSON parse success (no _parse_error means success)
                if "_parse_error" not in result:
                    json_ok += 1
                else:
                    errors.append({
                        "input": user_input,
                        "error": result["_parse_error"],
                        "expected": expected_type,
                    })

                # Check expert_type accuracy
                actual_type = result.get("expert_type", "")
                type_counts[actual_type] += 1
                if actual_type == expected_type:
                    type_correct += 1

                status = "✅" if "_parse_error" not in result else "❌"
                match = "✓" if actual_type == expected_type else "✗"
                print(f"  [{total:3d}/100] {status} JSON | {match} Type({actual_type}) | {elapsed_ms:.0f}ms | {user_input[:30]}")

            except Exception as e:
                elapsed_ms = (time.time() - start) * 1000
                latencies.append(elapsed_ms)
                errors.append({
                    "input": user_input,
                    "error": str(e),
                    "expected": expected_type,
                })
                print(f"  [{total:3d}/100] 💥 Exception: {e}")

    # ── Results ──
    json_rate = (json_ok / total * 100) if total > 0 else 0
    type_rate = (type_correct / total * 100) if total > 0 else 0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    print()
    print("=" * 60)
    print("验证结论")
    print("=" * 60)
    print(f"  JSON解析成功率:       {json_ok}/{total} = {json_rate:.1f}%  {'✅ PASS' if json_rate >= 95 else '❌ FAIL (需启用grammar)'}")
    print(f"  expert_type准确率:    {type_correct}/{total} = {type_rate:.1f}%")
    print(f"  平均响应时间:         {avg_latency:.0f}ms")
    print(f"  类型分布:             {dict(type_counts)}")
    print()

    if json_rate < 95:
        print("  ⚠️  JSON成功率不达标，建议启用 grammar 约束重新测试:")
        print("     python -m offgrid.validation.v1_gate_stability --grammar")
        print()

    if errors:
        print(f"  失败样本 ({len(errors)} 条):")
        for e in errors[:10]:
            print(f"    - [{e['expected']}] {e['input'][:40]} → {e['error'][:60]}")

    # ── Write conclusion ──
    conclusion = {
        "json_parse_rate": round(json_rate, 1),
        "expert_type_accuracy": round(type_rate, 1),
        "avg_latency_ms": round(avg_latency, 0),
        "grammar_used": use_grammar,
        "needs_grammar": json_rate < 95,
        "total_tests": total,
        "errors_count": len(errors),
    }

    import os
    conclusion_path = os.path.join(os.path.dirname(__file__), "v1_conclusion.json")
    with open(conclusion_path, "w", encoding="utf-8") as f:
        json.dump(conclusion, f, indent=2, ensure_ascii=False)
    print(f"\n  结论已保存到: {conclusion_path}")

    return conclusion


def main():
    parser = argparse.ArgumentParser(description="V1 Gate JSON稳定性验证")
    parser.add_argument("--model-path", type=str, default=None, help="本地GGUF模型路径")
    parser.add_argument("--ollama-url", type=str, default="http://localhost:11434")
    parser.add_argument("--ollama-model", type=str, default="qwen3-8b")
    parser.add_argument("--grammar", action="store_true", help="启用JSON grammar约束")
    args = parser.parse_args()

    run_validation(
        model_path=args.model_path,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        use_grammar=args.grammar,
    )


if __name__ == "__main__":
    main()
