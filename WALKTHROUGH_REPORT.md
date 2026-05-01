# OffGrid 系统走查报告（qwen3:8b 真实模型测试）

> 日期：2026-04-30
> 模型：qwen3:8b (Q4_K_M, 本地 Ollama)
> 方法：10 个复合场景端到端追踪，真实 LLM 调用验证

---

## 测试结果总览

| # | 场景 | Gate分类 | 核心机制 | 结果 | 问题 |
|---|------|---------|---------|------|------|
| 1 | 搜索天气做网页 | codegen/hard/search=true/hint="搜索天气数据,生成展示网页" | Gate新字段 | ✅ PASS | — |
| 2 | 修复JWT验证bug | locator_repair/easy/search=false | 单任务路由 | ✅ PASS | — |
| 3 | 你好今天天气 | chat/easy/search=true | chat分类 | ⚠️ | needs_search=true但chat不走预搜索（低优先级，ChatExpert内部有搜索） |
| 4 | 重构拆函数 | refactor/easy/search=false | 重构路由 | ✅ PASS | — |
| 5 | FastAPI+JWT | codegen/hard/search=true/hint=4个子任务 | 复杂hint | ✅ PASS | — |
| 6 | auto_decompose真实拆分 | — | Planner DAG生成 | ✅ PASS（修复后） | 🔴 regex非贪婪bug（已修） |
| 7 | auto_decompose复杂hint | — | 4子任务DAG | ✅ PASS（修复后） | 同上 |
| 8 | QueryGenerator site限定 | — | 搜索query生成 | ✅ PASS | LLM正确输出site:arxiv.org |
| 9 | QueryGenerator debug | — | 错误搜索 | ✅ PASS | LLM正确输出site:stackoverflow.com |
| 10 | Token tracking | — | 预算管控 | ✅ PASS | 3次调用共639 tokens |

---

## 发现的问题（按严重度排序）

### 🔴 Bug（会导致运行时错误）

**Issue 1: Planner._build_dag_from_hints regex 非贪婪匹配**
- 文件：`offgrid/core/planner.py`
- 原因：`re.search(r'\[.*?\]', raw, re.DOTALL)` 遇到 `depends_on: []` 时在第一个 `]` 处终止
- 影响：auto_decompose 永远返回 None（LLM 输出正确但解析失败）
- 状态：✅ 已修复（改为贪婪 `r'\[.*\]'`）

**Issue 2: TrajectoryCollector.get_by_expert() 方法不存在**
- 文件：`offgrid/flywheel/ab_tester.py` 调用 `self.collector.get_by_expert(expert_name)`
- 文件：`offgrid/flywheel/trajectory_collector.py` 没有这个方法
- 影响：专家投产后触发 PromptOptimizer 时 AttributeError
- 状态：❌ 待修复

### 🟡 空架子（功能存在但未接入）

**Issue 3: session_md.py 未接入 REPL 退出路径**
- 文件：`offgrid/memory/session_md.py` 有 `save_session()` 和 `load_session()`
- 文件：`offgrid/cli/main.py` 没有导入也没有调用
- 影响：SESSION.md 永远不会被写入，会话连续性是空架子
- 状态：❌ 待修复

**Issue 4: auto_decompose 未接入 _run_task()**
- 文件：`offgrid/core/planner.py` 有 `auto_decompose()` 方法
- 文件：`offgrid/cli/main.py` 的 `_run_task()` 没有调用它
- 影响：hard 任务不会自动拆分，只能手动 /multi
- 状态：❌ 待修复

**Issue 5: 预搜索（pre_search_results）未接入 _run_task()**
- 文件：`offgrid/core/orchestrator.py` 的 `run()` 接受 `pre_search_results` 参数
- 文件：`offgrid/cli/main.py` 的 `_run_task()` 没有传这个参数
- 影响：Gate 判断 needs_search=true 但预搜索不会触发
- 状态：❌ 待修复

### 🟢 功能缺失（不是 bug，是设计未覆盖）

**Issue 6: ChatExpert 无法执行 SSH 命令**
- ChatExpert 只有 search_augmentor，没有 ToolExecutor
- 用户说"帮我连VPS看nginx"时，agent 无法执行 ssh
- 需要：给 ChatExpert 注入 ToolExecutor 或新增 "ops" expert_type
- 状态：设计决策待定

**Issue 7: chat + needs_search=true 时预搜索不触发**
- Gate 对"今天天气怎么样"输出 chat + needs_search=true
- 但 chat 类型直接走 ChatExpert，不经过 _run_task 的预搜索逻辑
- 影响低：ChatExpert 内部有自己的搜索门控
- 状态：可接受（ChatExpert 内部处理）

---

## 机制验证结论

| 机制 | 状态 | 备注 |
|------|------|------|
| Gate 新字段（needs_search/subtask_hint） | ✅ 工作正常 | 8B模型输出格式正确 |
| 专家关键词匹配叠加 | ✅ 工作正常 | — |
| 动态重试预算 | ✅ 代码正确 | 未真实触发（需要失败场景） |
| Planner.auto_decompose | ✅ 修复后正常 | 8B模型能正确生成DAG |
| QueryGenerator site限定 | ✅ 工作正常 | 8B模型自动判断arxiv/stackoverflow |
| Token tracking | ✅ 工作正常 | 估算值合理 |
| DebugSubagent | ✅ 已实例化 | 需要verifier失败才触发 |
| Reviewer | ✅ 代码正确 | 需要verifier成功才触发 |
| PCED-Lite | ✅ 代码正确 | 需要3+搜索结果才触发 |
| session_md | ❌ 未接入 | save_session从未被调用 |
| auto_decompose接入 | ❌ 未接入 | _run_task里没有调用 |
| 预搜索接入 | ❌ 未接入 | pre_search_results未传递 |
| PromptOptimizer | ❌ get_by_expert不存在 | 投产时会报错 |

---

## 根因分析

4 个待修复问题的共同根因：**Spec 写了实现方案，模块代码写了，但"胶水代码"（在 main.py 里调用新模块）没写。**

这和 CODE_REVIEW_LESSONS.md 里总结的"空架子问题"完全一致——模块写完了但没有接入调用链。

---

*走查完成。待修复 4 个问题后再次验证。*
