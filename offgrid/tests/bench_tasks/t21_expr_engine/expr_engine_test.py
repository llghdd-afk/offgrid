import pytest
from expr_engine import (
    Environment, Literal, Variable, BinaryOp, IfExpr,
    LetExpr, Lambda, Apply, Closure, clear_cache, reset_depth,
    MAX_EVAL_DEPTH,
)


@pytest.fixture(autouse=True)
def clean_state():
    """Reset global caches and depth counter between tests."""
    clear_cache()
    reset_depth()
    yield
    clear_cache()
    reset_depth()


# ---------------------------------------------------------------------------
# Environment basics
# ---------------------------------------------------------------------------

class TestEnvironment:
    def test_lookup_simple(self):
        env = Environment({"x": 10})
        assert env.lookup("x") == 10

    def test_lookup_parent(self):
        parent = Environment({"a": 1})
        child = Environment({"b": 2}, parent=parent)
        assert child.lookup("a") == 1
        assert child.lookup("b") == 2

    def test_lookup_shadow(self):
        parent = Environment({"x": 1})
        child = parent.extend("x", 99)
        assert child.lookup("x") == 99
        assert parent.lookup("x") == 1

    def test_lookup_undefined(self):
        env = Environment()
        with pytest.raises(NameError, match="Undefined variable"):
            env.lookup("missing")

    def test_fingerprint_changes_with_binding(self):
        env1 = Environment({"x": 1})
        env2 = Environment({"x": 2})
        assert env1.fingerprint() != env2.fingerprint()


# ---------------------------------------------------------------------------
# Literal and Variable
# ---------------------------------------------------------------------------

class TestLiteralAndVariable:
    def test_literal_int(self):
        assert Literal(42).evaluate(Environment()) == 42

    def test_literal_string(self):
        assert Literal("hello").evaluate(Environment()) == "hello"

    def test_literal_bool(self):
        assert Literal(True).evaluate(Environment()) is True

    def test_variable_lookup(self):
        env = Environment({"x": 7})
        assert Variable("x").evaluate(env) == 7

    def test_variable_undefined(self):
        with pytest.raises(NameError):
            Variable("z").evaluate(Environment())


# ---------------------------------------------------------------------------
# BinaryOp — arithmetic
# ---------------------------------------------------------------------------

class TestBinaryOpArithmetic:
    def test_add(self):
        expr = BinaryOp("+", Literal(3), Literal(4))
        assert expr.evaluate(Environment()) == 7

    def test_sub(self):
        expr = BinaryOp("-", Literal(10), Literal(3))
        assert expr.evaluate(Environment()) == 7

    def test_mul(self):
        expr = BinaryOp("*", Literal(6), Literal(7))
        assert expr.evaluate(Environment()) == 42

    def test_div_exact(self):
        expr = BinaryOp("/", Literal(10), Literal(2))
        assert expr.evaluate(Environment()) == 5.0

    def test_div_fractional(self):
        """7 / 2 must return 3.5, not 3."""
        expr = BinaryOp("/", Literal(7), Literal(2))
        assert expr.evaluate(Environment()) == 3.5

    def test_div_negative_fractional(self):
        """-7 / 2 must return -3.5, not -4 (which // gives)."""
        expr = BinaryOp("/", Literal(-7), Literal(2))
        assert expr.evaluate(Environment()) == -3.5

    def test_div_by_zero(self):
        expr = BinaryOp("/", Literal(1), Literal(0))
        with pytest.raises(ZeroDivisionError):
            expr.evaluate(Environment())


# ---------------------------------------------------------------------------
# BinaryOp — comparison
# ---------------------------------------------------------------------------

class TestBinaryOpComparison:
    def test_eq_true(self):
        expr = BinaryOp("==", Literal(5), Literal(5))
        assert expr.evaluate(Environment()) is True

    def test_eq_false(self):
        expr = BinaryOp("==", Literal(5), Literal(6))
        assert expr.evaluate(Environment()) is False

    def test_neq(self):
        expr = BinaryOp("!=", Literal(1), Literal(2))
        assert expr.evaluate(Environment()) is True

    def test_lt(self):
        expr = BinaryOp("<", Literal(3), Literal(5))
        assert expr.evaluate(Environment()) is True

    def test_gt(self):
        expr = BinaryOp(">", Literal(5), Literal(3))
        assert expr.evaluate(Environment()) is True


# ---------------------------------------------------------------------------
# BinaryOp — short-circuit logic
# ---------------------------------------------------------------------------

class TestShortCircuit:
    def test_and_short_circuit_false(self):
        """False and (1/0) should return False, not raise ZeroDivisionError."""
        bomb = BinaryOp("/", Literal(1), Literal(0))
        expr = BinaryOp("and", Literal(False), bomb)
        result = expr.evaluate(Environment())
        assert result is False

    def test_and_both_true(self):
        expr = BinaryOp("and", Literal(3), Literal(5))
        assert expr.evaluate(Environment()) == 5

    def test_or_short_circuit_true(self):
        """True or (1/0) should return True, not raise ZeroDivisionError."""
        bomb = BinaryOp("/", Literal(1), Literal(0))
        expr = BinaryOp("or", Literal(True), bomb)
        result = expr.evaluate(Environment())
        assert result is True

    def test_or_both_false(self):
        expr = BinaryOp("or", Literal(False), Literal(42))
        assert expr.evaluate(Environment()) == 42

    def test_or_short_circuit_with_variable(self):
        """Ensure short-circuit works when right side would raise NameError."""
        undefined_var = Variable("does_not_exist")
        expr = BinaryOp("or", Literal(True), undefined_var)
        result = expr.evaluate(Environment())
        assert result is True

    def test_and_evaluates_right_when_left_truthy(self):
        """When left is truthy, 'and' must evaluate and return right."""
        expr = BinaryOp("and", Literal(1), Literal("yes"))
        assert expr.evaluate(Environment()) == "yes"


# ---------------------------------------------------------------------------
# IfExpr
# ---------------------------------------------------------------------------

class TestIfExpr:
    def test_if_true(self):
        expr = IfExpr(Literal(True), Literal("yes"), Literal("no"))
        assert expr.evaluate(Environment()) == "yes"

    def test_if_false(self):
        expr = IfExpr(Literal(False), Literal("yes"), Literal("no"))
        assert expr.evaluate(Environment()) == "no"

    def test_if_does_not_eval_other_branch(self):
        """Only the taken branch should be evaluated."""
        bomb = BinaryOp("/", Literal(1), Literal(0))
        expr = IfExpr(Literal(True), Literal(42), bomb)
        assert expr.evaluate(Environment()) == 42


# ---------------------------------------------------------------------------
# LetExpr
# ---------------------------------------------------------------------------

class TestLetExpr:
    def test_simple_let(self):
        # let x = 5 in x + 1
        expr = LetExpr("x", Literal(5),
                        BinaryOp("+", Variable("x"), Literal(1)))
        assert expr.evaluate(Environment()) == 6

    def test_nested_let(self):
        # let x = 2 in (let y = 3 in x * y)
        expr = LetExpr("x", Literal(2),
                        LetExpr("y", Literal(3),
                                BinaryOp("*", Variable("x"), Variable("y"))))
        assert expr.evaluate(Environment()) == 6

    def test_let_shadow(self):
        # let x = 1 in (let x = 2 in x)
        expr = LetExpr("x", Literal(1),
                        LetExpr("x", Literal(2), Variable("x")))
        assert expr.evaluate(Environment()) == 2


# ---------------------------------------------------------------------------
# Lambda / Apply basics
# ---------------------------------------------------------------------------

class TestLambdaApply:
    def test_identity(self):
        # (lambda x. x)(42)
        identity = Lambda("x", Variable("x"))
        expr = Apply(identity, Literal(42))
        assert expr.evaluate(Environment()) == 42

    def test_add_one(self):
        # (lambda x. x + 1)(9)
        fn = Lambda("x", BinaryOp("+", Variable("x"), Literal(1)))
        expr = Apply(fn, Literal(9))
        assert expr.evaluate(Environment()) == 10

    def test_apply_non_function(self):
        expr = Apply(Literal(42), Literal(1))
        with pytest.raises(TypeError, match="Cannot apply non-function"):
            expr.evaluate(Environment())


# ---------------------------------------------------------------------------
# Closure / variable capture
# ---------------------------------------------------------------------------

class TestClosureCapture:
    def test_closure_captures_at_creation_time(self):
        """
        let x = 10 in
          let f = (lambda y. x + y) in
            let x = 999 in
              f(1)
        Expected: 11 (f captured x=10 at its creation, not x=999)
        """
        expr = LetExpr("x", Literal(10),
                        LetExpr("f",
                                Lambda("y", BinaryOp("+", Variable("x"), Variable("y"))),
                                LetExpr("x", Literal(999),
                                        Apply(Variable("f"), Literal(1)))))
        assert expr.evaluate(Environment()) == 11

    def test_closure_not_affected_by_later_bindings(self):
        """
        let a = 5 in
          let get_a = (lambda _. a) in
            let a = 100 in
              get_a(0)
        Expected: 5
        """
        expr = LetExpr("a", Literal(5),
                        LetExpr("get_a",
                                Lambda("_", Variable("a")),
                                LetExpr("a", Literal(100),
                                        Apply(Variable("get_a"), Literal(0)))))
        assert expr.evaluate(Environment()) == 5

    def test_higher_order_closure(self):
        """
        let make_adder = (lambda x. (lambda y. x + y)) in
          let add3 = make_adder(3) in
            add3(10)
        Expected: 13
        """
        make_adder = Lambda("x", Lambda("y",
                            BinaryOp("+", Variable("x"), Variable("y"))))
        expr = LetExpr("make_adder", make_adder,
                        LetExpr("add3",
                                Apply(Variable("make_adder"), Literal(3)),
                                Apply(Variable("add3"), Literal(10))))
        assert expr.evaluate(Environment()) == 13


# ---------------------------------------------------------------------------
# Recursion depth
# ---------------------------------------------------------------------------

class TestRecursionDepth:
    def test_deep_recursion_raises_clean_error(self):
        """
        Build a recursive function that never terminates:
          let f = (lambda x. f(x)) in f(0)
        Should raise a clean RuntimeError about depth, NOT Python's
        built-in RecursionError.
        """
        env = Environment()
        body = Apply(Variable("f"), Variable("x"))
        fn = Lambda("x", body)
        expr = LetExpr("f", fn, Apply(Variable("f"), Literal(0)))
        try:
            expr.evaluate(env)
            assert False, "Should have raised an error"
        except RecursionError:
            pytest.fail("Got Python RecursionError; expected a clean RuntimeError "
                        "with a depth-exceeded message instead")
        except RuntimeError as exc:
            assert "depth" in str(exc).lower(), (
                f"RuntimeError should mention depth, got: {exc}"
            )

    def test_moderate_recursion_works(self):
        """
        Factorial-like: let fact = ... in fact(5)
        fact(n) = if n == 0 then 1 else n * fact(n-1)
        Should succeed without hitting depth limit.
        """
        env = Environment()
        # fact(n) = if n==0 then 1 else n * fact(n-1)
        cond = BinaryOp("==", Variable("n"), Literal(0))
        then_br = Literal(1)
        else_br = BinaryOp("*", Variable("n"),
                           Apply(Variable("fact"),
                                 BinaryOp("-", Variable("n"), Literal(1))))
        fact_body = IfExpr(cond, then_br, else_br)
        fact_fn = Lambda("n", fact_body)
        expr = LetExpr("fact", fact_fn, Apply(Variable("fact"), Literal(5)))
        assert expr.evaluate(env) == 120


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------

class TestCacheInvalidation:
    def test_same_expr_different_env(self):
        """
        The same Variable('x') node evaluated in two different environments
        must return different values — cache must not serve stale results.
        """
        var_x = Variable("x")
        env1 = Environment({"x": 100})
        env2 = Environment({"x": 200})
        assert var_x.evaluate(env1) == 100
        assert var_x.evaluate(env2) == 200  # must NOT return cached 100

    def test_let_rebinding_invalidates_cache(self):
        """
        let x = 1 in (x + (let x = 2 in x))
        Expected: 1 + 2 = 3
        The inner Variable('x') must see x=2, not cached x=1.
        """
        inner_x = Variable("x")
        outer_x = Variable("x")
        expr = LetExpr("x", Literal(1),
                        BinaryOp("+", outer_x,
                                 LetExpr("x", Literal(2), inner_x)))
        assert expr.evaluate(Environment()) == 3

    def test_cache_does_not_cross_function_scopes(self):
        """
        let x = 1 in
          let f = (lambda y. x + y) in
            let x = 100 in
              x + f(0)
        Expected: 100 + (1+0) = 101
        x inside f's closure must still be 1, despite x=100 outside.
        """
        inner_x = Variable("x")
        expr = LetExpr("x", Literal(1),
                        LetExpr("f",
                                Lambda("y", BinaryOp("+", Variable("x"), Variable("y"))),
                                LetExpr("x", Literal(100),
                                        BinaryOp("+", Variable("x"),
                                                 Apply(Variable("f"), Literal(0))))))
        # Both bugs (closure + cache) must be fixed for this to pass.
        assert expr.evaluate(Environment()) == 101


# ---------------------------------------------------------------------------
# Integration / combined scenarios
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_compound_expression(self):
        """
        let a = 10 in
          let b = 20 in
            if a < b then a + b else a - b
        Expected: 30
        """
        expr = LetExpr("a", Literal(10),
                        LetExpr("b", Literal(20),
                                IfExpr(BinaryOp("<", Variable("a"), Variable("b")),
                                       BinaryOp("+", Variable("a"), Variable("b")),
                                       BinaryOp("-", Variable("a"), Variable("b")))))
        assert expr.evaluate(Environment()) == 30

    def test_short_circuit_in_if_condition(self):
        """
        if (False and (1/0)) then 'boom' else 'safe'
        Expected: 'safe' — short-circuit prevents the division by zero.
        """
        bomb = BinaryOp("/", Literal(1), Literal(0))
        cond = BinaryOp("and", Literal(False), bomb)
        expr = IfExpr(cond, Literal("boom"), Literal("safe"))
        assert expr.evaluate(Environment()) == "safe"

    def test_division_in_let(self):
        """
        let ratio = 7 / 2 in ratio + 0.5
        Expected: 4.0 (ratio must be 3.5, not 3)
        """
        expr = LetExpr("ratio",
                        BinaryOp("/", Literal(7), Literal(2)),
                        BinaryOp("+", Variable("ratio"), Literal(0.5)))
        assert expr.evaluate(Environment()) == 4.0

    def test_nested_apply(self):
        """
        let twice = (lambda f. (lambda x. f(f(x)))) in
          let inc = (lambda n. n + 1) in
            twice(inc)(0)
        Expected: 2
        """
        twice = Lambda("f", Lambda("x",
                        Apply(Variable("f"),
                              Apply(Variable("f"), Variable("x")))))
        inc = Lambda("n", BinaryOp("+", Variable("n"), Literal(1)))
        expr = LetExpr("twice", twice,
                        LetExpr("inc", inc,
                                Apply(Apply(Variable("twice"), Variable("inc")),
                                      Literal(0))))
        assert expr.evaluate(Environment()) == 2
