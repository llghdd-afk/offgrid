import pytest
from calculator import Calculator


class TestBasicArithmetic:
    def test_addition(self):
        c = Calculator()
        assert c.evaluate("2 + 3") == 5.0

    def test_subtraction(self):
        c = Calculator()
        assert c.evaluate("10 - 4") == 6.0

    def test_multiplication(self):
        c = Calculator()
        assert c.evaluate("3 * 7") == 21.0

    def test_division(self):
        c = Calculator()
        assert c.evaluate("15 / 4") == 3.75

    def test_operator_precedence(self):
        c = Calculator()
        assert c.evaluate("2 + 3 * 4") == 14.0

    def test_left_associativity_sub(self):
        c = Calculator()
        assert c.evaluate("10 - 3 - 2") == 5.0

    def test_left_associativity_div(self):
        c = Calculator()
        assert c.evaluate("100 / 5 / 4") == 5.0


class TestNegativeNumbers:
    def test_unary_minus(self):
        c = Calculator()
        assert c.evaluate("-5") == -5.0

    def test_unary_minus_in_expr(self):
        c = Calculator()
        assert c.evaluate("3 + -2") == 1.0

    def test_multiply_negative(self):
        c = Calculator()
        assert c.evaluate("3 * -2") == -6.0

    def test_double_negative(self):
        c = Calculator()
        assert c.evaluate("--5") == 5.0

    def test_negative_in_parens(self):
        c = Calculator()
        assert c.evaluate("(-3) * 4") == -12.0


class TestParentheses:
    def test_simple_parens(self):
        c = Calculator()
        assert c.evaluate("(2 + 3) * 4") == 20.0

    def test_nested_parens(self):
        c = Calculator()
        assert c.evaluate("((2 + 3) * (4 - 1))") == 15.0

    def test_parens_override_precedence(self):
        c = Calculator()
        assert c.evaluate("2 * (3 + 4)") == 14.0


class TestDivisionByZero:
    def test_divide_by_zero(self):
        c = Calculator()
        with pytest.raises(ZeroDivisionError):
            c.evaluate("5 / 0")

    def test_divide_by_zero_expr(self):
        c = Calculator()
        with pytest.raises(ZeroDivisionError):
            c.evaluate("10 / (3 - 3)")


class TestVariables:
    def test_simple_var(self):
        c = Calculator()
        c.set_var("x", 10)
        assert c.evaluate("x + 5") == 15.0

    def test_multiple_vars(self):
        c = Calculator()
        c.set_var("a", 3)
        c.set_var("b", 4)
        assert c.evaluate("a * a + b * b") == 25.0

    def test_undefined_var(self):
        c = Calculator()
        with pytest.raises(NameError):
            c.evaluate("x + 1")

    def test_var_update(self):
        c = Calculator()
        c.set_var("x", 5)
        assert c.evaluate("x * 2") == 10.0
        c.set_var("x", 10)
        assert c.evaluate("x * 2") == 20.0


class TestComplex:
    def test_complex_expression(self):
        c = Calculator()
        c.set_var("pi", 3.14159)
        c.set_var("r", 5)
        # area = pi * r * r
        result = c.evaluate("pi * r * r")
        assert abs(result - 78.53975) < 0.001

    def test_deeply_nested(self):
        c = Calculator()
        assert c.evaluate("((((1 + 2) * 3) - 4) / 5)") == 1.0

    def test_whitespace_variations(self):
        c = Calculator()
        assert c.evaluate("  2+3 * 4  ") == 14.0

    def test_decimal_numbers(self):
        c = Calculator()
        assert abs(c.evaluate("1.5 * 2.5") - 3.75) < 0.001
