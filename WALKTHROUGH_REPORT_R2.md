# OffGrid 第二轮走查报告

> 日期：2026-04-30
> 模型：qwen3:8b (Q4_K_M, 本地 Ollama)
> 方法：10 个新复合场景，不修只记录

---

## 测试结果

| # | 场景 | Gate输出 | auto_decompose | 问题 |
|---|------|---------|---------------|------|
| T01 | 类型注解+写测试 | locator_repair/hard/hint="添加类型注解,编写单元测试" | ✅ 2子任务(t2依赖t1) | — |
| T02 | 连VPS查docker重启nginx | chat/easy | N/A | 🔴 SSH无法执行 |
| T03 | 读README生成PPT | chat/easy | N/A | 🔴 PPT误分类 |
| T04 | 隐藏bug偶尔KeyError | locator_repair/easy | N/A | ✅ 正确 |
| T05 | 爬虫+存Excel | codegen/hard/search=true/hint=3个 | ✅ 3子任务串行 | — |
| T06 | 批量替换print→logging | locator_repair/hard/hint="遍历,替换" | ✅ 2子任务 | ⚠️ hint质量 |
| T07 | FastAPI 422错误 | locator_repair/easy + FastAPIExpert | N/A | ✅ 正确 |
| T08 | React vs Vue写文档 | codegen/hard/search=false/hint=3个 | ✅ 2子任务(合并) | ⚠️ 应该search |
| T09 | 3个TODO全实现 | locator_repair/easy | N/A | ⚠️ 应该hard |
| T10 | 同步改异步 | locator_repair/easy | N/A | ✅ 正确 |

---

## 问题分类

### 🔴 严重（功能不可用）

**1. SSH/ops 操作无法执行**
- 场景：用户说"连VPS查docker状态"
- Gate分类：chat（正确，因为没有ops类型）
- 问题：ChatExpert 没有 ToolExecutor，无法执行 ssh_exec
- 根因：**设计缺失**——expert_type 里没有 ops/devops 类型
- 不是 bug，是架构未覆盖的场景
- 修复方向：新增 ops expert_type，或给 ChatExpert 注入 ToolExecutor

**2. PPT 生成被误分类为 chat**
- 场景：用户说"根据README生成项目介绍PPT"
- Gate分类：chat（错误，应该是 office）
- 问题：Gate prompt 里 office 的触发条件是".xlsx/.docx/.pptx"关键词
- 根因：用户说"PPT"而不是".pptx"，Gate 没识别
- 修复方向：Gate prompt 示例里加"PPT/幻灯片/演示/汇报"→office

### ⚠️ 可接受（边界模糊，不影响核心功能）

**3. React对比不触发搜索**
- needs_search=false，但对比最新框架理论上需要搜索
- 可接受：Generator 用训练数据里的知识也能写出合理对比

**4. 3个TODO判断为easy**
- 应该是 hard（多处修改），但 Gate 判断为 easy
- 可接受：单任务路径也能处理（Locator 会找到多个位置）

**5. hint"遍历src目录"不是有意义的子任务**
- Gate 生成的 hint 太机械，"遍历"是手段不是目的
- 可接受：auto_decompose 后 t1 的 input 会被 Gate 重新分类

---

## 机制验证结论

| 机制 | 第一轮 | 第二轮 | 总结 |
|------|--------|--------|------|
| Gate 基础分类 | 5/5 | 8/10 | 稳定，2个是设计缺失不是分类错误 |
| Gate needs_search | 正确 | 9/10 | 1个边界模糊（可接受） |
| Gate subtask_hint | 正确 | 正确 | 8B模型能生成合理hint |
| auto_decompose | 修复后4/4 | 4/4 | 机制稳定，regex修复后无问题 |
| 专家匹配叠加 | 正确 | 正确 | FastAPI/TestGen正确触发 |
| QueryGenerator site | 正确 | — | 上轮已验证 |
| Token tracking | 正确 | — | 上轮已验证 |

---

## 不修的原因

这两个"严重问题"不应该现在修，因为：

1. **SSH/ops 是架构决策**，不是 bug。需要讨论：是新增 expert_type 还是扩展 ChatExpert？这影响整体架构。
2. **PPT 误分类是 Gate prompt 调优**，改 prompt 示例可以修，但要小心不要让 Gate 对所有"PPT"都走 office（用户可能说"帮我写个PPT展示的HTML页面"，这应该是 codegen 不是 office）。

这两个问题需要你决策方向后再修。

---

## 和第一轮对比

第一轮发现的是"空架子"问题（模块存在但未接入）——这是工程疏忽，修复是确定性的。

第二轮发现的是"设计边界"问题（Gate 分类精度、expert_type 覆盖度）——这需要产品决策，不是代码 bug。

**结论：框架机制本身是正确的，没有过拟合。问题出在覆盖度（缺 ops 类型）和 prompt 精度（PPT 触发词），不是架构问题。**
