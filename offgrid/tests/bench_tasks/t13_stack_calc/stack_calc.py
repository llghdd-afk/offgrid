"""
Stack Calculator — 支持四则运算和括号的表达式计算器

使用调度场算法 (Shunting-Yard) 将中缀表达式转换为后缀 (逆波兰) 表达式，
然后用栈求值。

需要实现：
1. tokenize(expr) - 词法分析
2. infix_to_postfix(tokens) - 中缀转后缀
3. eval_postfix(tokens) - 后缀表达式求值
4. calculate(expr) - 主入口
"""


class CalculatorError(Exception):
    """计算器错误"""
    pass


def tokenize(expr: str) -> list:
    """
    将表达式字符串分割为 token 列表。

    支持：整数、小数、+、-、*、/、(、)
    负数的处理：在表达式开头或左括号后的 - 视为负号（一元运算符）

    示例：
        "3 + 4 * 2" -> [3.0, '+', 4.0, '*', 2.0]
        "-(3+4)" -> [-1.0, '*', '(', 3.0, '+', 4.0, ')']
        "-5 + 3" -> [-5.0, '+', 3.0]
    """
    # TODO: 实现词法分析
    raise NotImplementedError("tokenize not implemented")


def infix_to_postfix(tokens: list) -> list:
    """
    使用调度场算法将中缀表达式 token 列表转换为后缀表达式。

    运算符优先级：
        +, - : 1
        *, / : 2

    所有运算符都是左结合的。

    示例：
        [3, '+', 4, '*', 2] -> [3, 4, 2, '*', '+']
        [(, 3, '+', 4, ), '*', 2] -> [3, 4, '+', 2, '*']
    """
    # TODO: 实现调度场算法
    raise NotImplementedError("infix_to_postfix not implemented")


def eval_postfix(tokens: list) -> float:
    """
    计算后缀表达式的值。

    遇到数字压栈，遇到运算符弹出两个操作数计算后压回。
    最终栈中应该只剩一个值。

    除以零应该抛出 CalculatorError。
    """
    # TODO: 实现后缀表达式求值
    raise NotImplementedError("eval_postfix not implemented")


def calculate(expr: str) -> float:
    """
    计算表达式的值。主入口函数。

    空表达式抛出 CalculatorError。
    非法表达式（括号不匹配等）抛出 CalculatorError。

    返回值：float 类型，整数结果返回 int 形式（如 6.0 -> 6）
    """
    # TODO: 组合以上三个函数
    raise NotImplementedError("calculate not implemented")
