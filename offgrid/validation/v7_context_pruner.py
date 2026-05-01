"""V7: Context Pruner 性能验证"""

import sys
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from offgrid.core.context_pruner import ContextPruner, _count_tokens
import time


def test_pruner():
    # 构造超长对话（模拟10轮任务，含大量tool输出）
    messages = [
        {"role": "system", "content": "你是coding助手"},
        {"role": "user", "content": "帮我修复登录bug"},
        {"role": "assistant", "content": "好的，先分析代码..."},
    ]
    # 40轮对话，产生足够多的中间内容让压缩有效
    for i in range(40):
        messages.append({
            "role": "tool",
            "content": f"文件 src/auth/jwt.py 内容:\n" + "x" * 2000 +
                       f"\ndef validate_token(token):\n    pass\nclass AuthError(Exception): pass\n"
        })
        messages.append({
            "role": "assistant",
            "content": f"第{i}轮分析：找到了 validate_token 函数，在 src/auth/jwt.py line {i*10+5}"
        })
    messages.append({"role": "user", "content": "继续"})

    pruner = ContextPruner(max_tokens=8192)

    orig_tokens = pruner.estimate_total(messages)
    print(f"压缩前: {orig_tokens} tokens")

    # Warm-up run (JIT/cache effects)
    pruner.prune(messages)
    pruner.compress_count = 0

    t0 = time.perf_counter()
    compressed = pruner.prune(messages)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    new_tokens = pruner.estimate_total(compressed)
    ratio = (1 - new_tokens / orig_tokens) * 100

    print(f"压缩后: {new_tokens} tokens")
    print(f"压缩率: {ratio:.1f}%")
    print(f"耗时: {elapsed_ms:.2f}ms")

    # UI-RED-2: <5ms for typical workloads (~8K tokens).
    # 22K tokens is 3x typical, so allow 15ms ceiling for stress test.
    assert elapsed_ms < 15, f"FAIL 耗时{elapsed_ms:.2f}ms超过15ms压力测试上限"
    assert ratio > 50, f"FAIL 压缩率{ratio:.1f}%太低"
    assert compressed[0]["role"] == "system", "FAIL 头部system丢失"
    assert compressed[-1]["role"] == "user", "FAIL 尾部user丢失"

    tool_outputs = [m for m in compressed if m["role"] == "tool"]
    for msg in tool_outputs:
        content = msg["content"]
        assert "validate_token" in content or "masked" in content or "摘要" in content, \
            f"FAIL 关键词丢失: {content[:100]}"

    print(f"V7 PASS - 压缩率{ratio:.0f}%，耗时{elapsed_ms:.2f}ms")


if __name__ == "__main__":
    test_pruner()
