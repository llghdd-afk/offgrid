---
name: TypeHintExpert
version: 1.0.0
trigger_keywords: [类型注解, type hint, typing, 类型标注, mypy]
trigger_min_confidence: 0.7
pipeline: [locator, generator]
lifecycle: mature
---

## 领域知识

- Python 3.10+用内置类型（list[str], dict[str, int], str | None），低版本用typing模块
- Optional[X]等价于X | None，表示可能为None，不表示"可选参数"
- 函数签名：所有公开函数标注参数类型和返回类型，内部函数可省略
- 泛型：TypeVar定义类型变量，Generic[T]创建泛型类，bound限制上界
- Protocol：结构化子类型（鸭子类型的静态版），定义接口不需要继承
- TypedDict：字典的精确类型，每个key有独立类型，total=False允许可选key
- Literal：限制值为几个字面量之一，如Literal["read", "write"]
- Callable[[参数类型], 返回类型]标注回调函数，参数多时用Protocol替代
- overload装饰器：同一函数不同参数组合返回不同类型时使用
- TYPE_CHECKING：避免运行时循环导入，仅在类型检查时导入

## 经验规则（自动生成）
