---
name: DocstringExpert
version: 1.0.0
trigger_keywords: [docstring, 注释, comment, 代码注释, 函数注释]
trigger_min_confidence: 0.7
pipeline: [locator, generator]
lifecycle: mature
---

## 领域知识

- 默认用Google风格docstring，项目已有NumPy风格则跟随
- 一行摘要用祈使句（"计算xxx"而非"这个函数计算xxx"）
- Args段：每个参数一行，格式 `name (type): 描述`
- Returns段：写明类型和含义，多返回值用tuple说明各元素
- Raises段：只列主动raise的异常，不列底层传播的
- 示例（Examples）：给出可直接运行的doctest片段
- 类docstring写在class行下方，描述职责而非实现
- 中文项目用中文写docstring，英文项目用英文，混合项目跟随已有风格
- 私有方法（_前缀）可省略docstring，公开API必须有
- 装饰器不影响docstring位置，始终写在def下一行

## 经验规则（自动生成）
