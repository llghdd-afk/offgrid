"""Tests for Stack Calculator"""

import pytest
from stack_calc import tokenize, infix_to_postfix, eval_postfix, calculate, CalculatorError


class TestTokenize:
    def test_simple_addition(self):
        assert tokenize("3 + 4") == [3.0, '+', 4.0]

    def test_no_spaces(self):
        assert tokenize("3+4") == [3.0, '+', 4.0]

    def test_all_operators(self):
        tokens = tokenize("1+2-3*4/5")
        assert tokens == [1.0, '+', 2.0, '-', 3.0, '*', 4.0, '/', 5.0]

    def test_parentheses(self):
        tokens = tokenize("(3 + 4) * 2")
        assert tokens == ['(', 3.0, '+', 4.0, ')', '*', 2.0]

    def test_decimal_numbers(self):
        tokens = tokenize("3.14 + 2.86")
        assert tokens == [3.14, '+', 2.86]

    def test_negative_at_start(self):
        tokens = tokenize("-5 + 3")
        assert tokens == [-5.0, '+', 3.0]

    def test_negative_after_paren(self):
        """负号在左括号后面应该处理为负数"""
        tokens = tokenize("(-5 + 3)")
        assert tokens == ['(', -5.0, '+', 3.0, ')']

    def test_negative_expression(self):
        """-(expr) 应该转换为 -1 * (expr)"""
        tokens = tokenize("-(3+4)")
        assert tokens == [-1.0, '*', '(', 3.0, '+', 4.0, ')']

    def test_multi_digit(self):
        tokens = tokenize("123 + 456")
        assert tokens == [123.0, '+', 456.0]


class TestInfixToPostfix:
    def test_simple_addition(self):
        assert infix_to_postfix([3.0, '+', 4.0]) == [3.0, 4.0, '+']

    def test_precedence(self):
        """乘法优先于加法"""
        result = infix_to_postfix([3.0, '+', 4.0, '*', 2.0])
        assert result == [3.0, 4.0, 2.0, '*', '+']

    def test_parentheses_override(self):
        """括号改变优先级"""
        result = infix_to_postfix(['(', 3.0, '+', 4.0, ')', '*', 2.0])
        assert result == [3.0, 4.0, '+', 2.0, '*']

    def test_left_associative(self):
        """左结合：3 - 2 - 1 = (3-2)-1 = 0"""
        result = infix_to_postfix([3.0, '-', 2.0, '-', 1.0])
        assert result == [3.0, 2.0, '-', 1.0, '-']

    def test_nested_parens(self):
        result = infix_to_postfix(['(', '(', 1.0, '+', 2.0, ')', '*', 3.0, ')'])
        assert result == [1.0, 2.0, '+', 3.0, '*']


class TestEvalPostfix:
    def test_addition(self):
        assert eval_postfix([3.0, 4.0, '+']) == 7.0

    def test_subtraction(self):
        assert eval_postfix([10.0, 3.0, '-']) == 7.0

    def test_multiplication(self):
        assert eval_postfix([3.0, 4.0, '*']) == 12.0

    def test_division(self):
        assert eval_postfix([10.0, 4.0, '/']) == 2.5

    def test_complex_expression(self):
        # 3 + 4 * 2 = 11
        assert eval_postfix([3.0, 4.0, 2.0, '*', '+']) == 11.0

    def test_division_by_zero(self):
        with pytest.raises(CalculatorError):
            eval_postfix([5.0, 0.0, '/'])


class TestCalculate:
    def test_simple(self):
        assert calculate("3 + 4") == 7

    def test_precedence(self):
        assert calculate("3 + 4 * 2") == 11

    def test_parentheses(self):
        assert calculate("(3 + 4) * 2") == 14

    def test_nested_parentheses(self):
        assert calculate("((1 + 2) * (3 + 4))") == 21

    def test_negative_number(self):
        assert calculate("-5 + 8") == 3

    def test_negative_expression(self):
        assert calculate("-(3 + 4)") == -7

    def test_decimal(self):
        assert abs(calculate("3.14 * 2") - 6.28) < 0.001

    def test_complex_expression(self):
        # 2 * (3 + 4) - 10 / 5 = 14 - 2 = 12
        assert calculate("2 * (3 + 4) - 10 / 5") == 12

    def test_left_associative_subtraction(self):
        assert calculate("10 - 3 - 2") == 5

    def test_left_associative_division(self):
        assert calculate("8 / 4 / 2") == 1

    def test_empty_expression(self):
        with pytest.raises(CalculatorError):
            calculate("")

    def test_division_by_zero(self):
        with pytest.raises(CalculatorError):
            calculate("1 / 0")

    def test_mismatched_parentheses(self):
        with pytest.raises(CalculatorError):
            calculate("(3 + 4")

    def test_integer_result(self):
        """整数结果应该返回 int 类型或等价的 float"""
        result = calculate("6 / 2")
        assert result == 3

    def test_whitespace_handling(self):
        assert calculate("  3  +  4  ") == 7
