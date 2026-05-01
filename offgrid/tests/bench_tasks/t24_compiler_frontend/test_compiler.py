"""Tests for the mini-language compiler frontend (lexer + parser + evaluator).

DO NOT MODIFY THIS FILE.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from lexer import Lexer, Token, TokenType
from parser import Parser, Block, NumberLit, StringLit, BoolLit, Ident, FnDef
from evaluator import Evaluator, Environment, Closure


# ── Helpers ────────────────────────────────────────────────

def run(source: str) -> Evaluator:
    """Tokenize, parse, and evaluate source; return evaluator for inspection."""
    tokens = Lexer(source).tokenize()
    ast = Parser(tokens).parse()
    ev = Evaluator()
    ev.run(ast)
    return ev


def eval_expr(source: str):
    """Evaluate source and return the last expression value."""
    tokens = Lexer(source).tokenize()
    ast = Parser(tokens).parse()
    ev = Evaluator()
    result = ev.run(ast)
    return result, ev


# ═══════════════════════════════════════════════════════════
#  LEXER TESTS
# ═══════════════════════════════════════════════════════════

class TestLexer:
    def test_numbers(self):
        tokens = Lexer("42 0 100").tokenize()
        nums = [t for t in tokens if t.type == TokenType.NUMBER]
        assert [t.value for t in nums] == ["42", "0", "100"]

    def test_keywords(self):
        tokens = Lexer("let fn if else while return print true false").tokenize()
        kws = [t for t in tokens if t.type == TokenType.KEYWORD]
        assert len(kws) == 9

    def test_identifiers(self):
        tokens = Lexer("foo bar_baz x1").tokenize()
        ids = [t for t in tokens if t.type == TokenType.IDENT]
        assert [t.value for t in ids] == ["foo", "bar_baz", "x1"]

    def test_operators(self):
        tokens = Lexer("+ - * / % == != < > <= >= && || !").tokenize()
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        assert TokenType.PLUS in types
        assert TokenType.EQEQ in types
        assert TokenType.AND in types
        assert TokenType.OR in types

    def test_simple_string(self):
        tokens = Lexer('"hello world"').tokenize()
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "hello world"

    def test_string_escape_newline(self):
        tokens = Lexer(r'"line1\nline2"').tokenize()
        assert tokens[0].value == "line1\nline2"

    def test_string_escape_tab(self):
        tokens = Lexer(r'"col1\tcol2"').tokenize()
        assert tokens[0].value == "col1\tcol2"

    def test_string_with_escaped_quote(self):
        """Escaped quotes inside strings must be handled."""
        source = r'"say \"hello\" world"'
        tokens = Lexer(source).tokenize()
        str_tok = tokens[0]
        assert str_tok.type == TokenType.STRING
        assert str_tok.value == 'say "hello" world'

    def test_string_escaped_quote_at_end(self):
        """Escaped quote right before end of string."""
        source = r'"value: \"test\""'
        tokens = Lexer(source).tokenize()
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == 'value: "test"'

    def test_comments_skipped(self):
        tokens = Lexer("42 // this is a comment\n 7").tokenize()
        nums = [t for t in tokens if t.type == TokenType.NUMBER]
        assert [t.value for t in nums] == ["42", "7"]

    def test_line_tracking(self):
        tokens = Lexer("a\nb\nc").tokenize()
        lines = [t.line for t in tokens if t.type == TokenType.IDENT]
        assert lines == [1, 2, 3]


# ═══════════════════════════════════════════════════════════
#  PARSER TESTS
# ═══════════════════════════════════════════════════════════

class TestParser:
    def test_let_statement(self):
        tokens = Lexer("let x = 42;").tokenize()
        ast = Parser(tokens).parse()
        assert len(ast.statements) == 1
        assert ast.statements[0].name == "x"

    def test_arithmetic_precedence(self):
        """2 + 3 * 4 should parse as 2 + (3 * 4)."""
        result, _ = eval_expr("let _ = 2 + 3 * 4;")
        # result is last eval value
        tokens = Lexer("let r = 2 + 3 * 4;").tokenize()
        ast = Parser(tokens).parse()
        # just check it parses
        assert ast is not None

    def test_function_definition(self):
        tokens = Lexer("let f = fn(a, b) { return a + b; };").tokenize()
        ast = Parser(tokens).parse()
        let_node = ast.statements[0]
        assert isinstance(let_node.value, FnDef)
        assert let_node.value.params == ["a", "b"]

    def test_if_else(self):
        tokens = Lexer("if (true) { 1; } else { 2; }").tokenize()
        ast = Parser(tokens).parse()
        assert ast is not None

    def test_while_loop(self):
        tokens = Lexer("while (true) { break; }").tokenize()
        ast = Parser(tokens).parse()
        assert ast is not None

    def test_nested_calls(self):
        tokens = Lexer("f(g(1), 2);").tokenize()
        ast = Parser(tokens).parse()
        assert ast is not None

    def test_unary_operators(self):
        tokens = Lexer("let x = -5; let y = !true;").tokenize()
        ast = Parser(tokens).parse()
        assert len(ast.statements) == 2


# ═══════════════════════════════════════════════════════════
#  EVALUATOR - BASIC TESTS
# ═══════════════════════════════════════════════════════════

class TestEvaluatorBasic:
    def test_arithmetic(self):
        result, _ = eval_expr("let x = 2 + 3 * 4;")
        assert result == 14

    def test_string_concatenation(self):
        result, _ = eval_expr('let s = "hello" + " " + "world";')
        assert result == "hello world"

    def test_boolean_ops(self):
        result, _ = eval_expr("let x = true && false;")
        assert result is False

    def test_comparison(self):
        result, _ = eval_expr("let x = 10 > 5;")
        assert result is True

    def test_let_and_use(self):
        result, _ = eval_expr("let x = 10; let y = x + 5;")
        assert result == 15

    def test_assignment(self):
        result, _ = eval_expr("let x = 1; x = 2; let y = x;")
        assert result == 2

    def test_unary_minus(self):
        result, _ = eval_expr("let x = -5;")
        assert result == -5

    def test_unary_not(self):
        result, _ = eval_expr("let x = !true;")
        assert result is False

    def test_modulo(self):
        result, _ = eval_expr("let x = 10 % 3;")
        assert result == 1

    def test_division(self):
        result, _ = eval_expr("let x = 10 / 3;")
        assert result == 3  # integer division


# ═══════════════════════════════════════════════════════════
#  EVALUATOR - CONTROL FLOW
# ═══════════════════════════════════════════════════════════

class TestControlFlow:
    def test_if_true(self):
        ev = run('if (true) { print("yes"); } else { print("no"); }')
        assert ev.output == ["yes"]

    def test_if_false(self):
        ev = run('if (false) { print("yes"); } else { print("no"); }')
        assert ev.output == ["no"]

    def test_if_numeric_truthy(self):
        ev = run('if (1) { print("truthy"); }')
        assert ev.output == ["truthy"]

    def test_if_zero_falsy(self):
        ev = run('if (0) { print("truthy"); } else { print("falsy"); }')
        assert ev.output == ["falsy"]

    def test_simple_while(self):
        source = """
        let i = 0;
        while (i < 5) {
            i = i + 1;
        }
        print(i);
        """
        ev = run(source)
        assert ev.output == ["5"]

    def test_while_with_break(self):
        source = """
        let i = 0;
        while (true) {
            if (i == 3) { break; }
            i = i + 1;
        }
        print(i);
        """
        ev = run(source)
        assert ev.output == ["3"]

    def test_while_with_continue(self):
        source = """
        let i = 0;
        let sum = 0;
        while (i < 10) {
            i = i + 1;
            if (i % 2 == 0) { continue; }
            sum = sum + i;
        }
        print(sum);
        """
        ev = run(source)
        assert ev.output == ["25"]  # 1+3+5+7+9

    def test_nested_while_break_inner_only(self):
        """Break in inner loop must NOT break outer loop."""
        source = """
        let outer_count = 0;
        let total = 0;
        while (outer_count < 3) {
            outer_count = outer_count + 1;
            let inner = 0;
            while (true) {
                inner = inner + 1;
                if (inner == 2) { break; }
            }
            total = total + inner;
        }
        print(outer_count);
        print(total);
        """
        ev = run(source)
        assert ev.output == ["3", "6"]

    def test_nested_while_independent_loops(self):
        """Outer loop runs all iterations despite inner break."""
        source = """
        let result = 0;
        let i = 0;
        while (i < 4) {
            i = i + 1;
            let j = 0;
            while (j < 100) {
                j = j + 1;
                if (j == 5) { break; }
            }
            result = result + j;
        }
        print(result);
        """
        ev = run(source)
        assert ev.output == ["20"]  # 4 iterations * 5 each


# ═══════════════════════════════════════════════════════════
#  EVALUATOR - FUNCTIONS
# ═══════════════════════════════════════════════════════════

class TestFunctions:
    def test_simple_function(self):
        source = """
        let add = fn(a, b) { return a + b; };
        let result = add(3, 4);
        print(result);
        """
        ev = run(source)
        assert ev.output == ["7"]

    def test_function_no_return(self):
        """Function without explicit return yields None (last expression value)."""
        source = """
        let f = fn(x) { let y = x + 1; };
        let r = f(5);
        """
        result, _ = eval_expr(source)
        # last expression in block is LetStmt which returns value
        assert result == 6

    def test_higher_order_function(self):
        source = """
        let apply = fn(f, x) { return f(x); };
        let double = fn(n) { return n * 2; };
        let result = apply(double, 5);
        print(result);
        """
        ev = run(source)
        assert ev.output == ["10"]

    def test_recursive_function(self):
        source = """
        let factorial = fn(n) {
            if (n <= 1) { return 1; }
            return n * factorial(n - 1);
        };
        print(factorial(5));
        """
        ev = run(source)
        assert ev.output == ["120"]

    def test_wrong_arg_count(self):
        source = """
        let f = fn(a, b) { return a + b; };
        f(1);
        """
        with pytest.raises(TypeError):
            run(source)


# ═══════════════════════════════════════════════════════════
#  EVALUATOR - SCOPE & CLOSURES
# ═══════════════════════════════════════════════════════════

class TestScopeAndClosures:
    def test_function_scope_isolation(self):
        """Variables defined inside function don't leak out."""
        source = """
        let x = 10;
        let f = fn() { let x = 99; return x; };
        let inner = f();
        print(inner);
        print(x);
        """
        ev = run(source)
        assert ev.output == ["99", "10"]

    def test_nested_scope_lookup(self):
        """Variable in intermediate scope must be found."""
        source = """
        let x = 1;
        let outer = fn() {
            let y = 10;
            let inner = fn() {
                return y;
            };
            return inner();
        };
        print(outer());
        """
        ev = run(source)
        assert ev.output == ["10"]

    def test_three_level_scope(self):
        """Three levels of nesting, middle scope variable."""
        source = """
        let a = 1;
        let f1 = fn() {
            let b = 20;
            let f2 = fn() {
                let f3 = fn() {
                    return a + b;
                };
                return f3();
            };
            return f2();
        };
        print(f1());
        """
        ev = run(source)
        assert ev.output == ["21"]

    def test_closure_factory(self):
        """Each closure from a factory must have its own scope."""
        source = """
        let make_adder = fn(n) {
            return fn(x) { return x + n; };
        };
        let add5 = make_adder(5);
        let add10 = make_adder(10);
        print(add5(1));
        print(add10(1));
        """
        ev = run(source)
        assert ev.output == ["6", "11"]

    def test_function_params_dont_pollute_closure(self):
        """Calling a function must not alter its closure env."""
        source = """
        let make_greeter = fn(greeting) {
            return fn(name) { return greeting + " " + name; };
        };
        let hello = make_greeter("hello");
        print(hello("alice"));
        print(hello("bob"));
        """
        ev = run(source)
        assert ev.output == ["hello alice", "hello bob"]

    def test_multiple_calls_independent(self):
        """Multiple calls to same function don't share params."""
        source = """
        let f = fn(x) { return x * 2; };
        print(f(3));
        print(f(5));
        print(f(7));
        """
        ev = run(source)
        assert ev.output == ["6", "10", "14"]

    def test_global_variable_accessible_in_function(self):
        source = """
        let g = 42;
        let f = fn() { return g; };
        print(f());
        """
        ev = run(source)
        assert ev.output == ["42"]

    def test_nested_scope_with_shadowing(self):
        """Shadowed variable in middle scope."""
        source = """
        let x = 1;
        let outer = fn() {
            let x = 50;
            let inner = fn() {
                return x;
            };
            return inner();
        };
        print(outer());
        """
        ev = run(source)
        assert ev.output == ["50"]


# ═══════════════════════════════════════════════════════════
#  INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════

class TestIntegration:
    def test_counter(self):
        """A counter using closures."""
        source = """
        let make_counter = fn(start) {
            let count = start;
            let inc = fn() {
                count = count + 1;
                return count;
            };
            return inc;
        };
        let c = make_counter(0);
        print(c());
        print(c());
        print(c());
        """
        ev = run(source)
        assert ev.output == ["1", "2", "3"]

    def test_fibonacci(self):
        source = """
        let fib = fn(n) {
            if (n <= 0) { return 0; }
            if (n == 1) { return 1; }
            return fib(n - 1) + fib(n - 2);
        };
        print(fib(0));
        print(fib(1));
        print(fib(6));
        """
        ev = run(source)
        assert ev.output == ["0", "1", "8"]

    def test_string_building_in_loop(self):
        source = """
        let result = "";
        let i = 0;
        while (i < 3) {
            result = result + "x";
            i = i + 1;
        }
        print(result);
        """
        ev = run(source)
        assert ev.output == ["xxx"]

    def test_nested_if(self):
        source = """
        let classify = fn(n) {
            if (n > 0) {
                if (n > 100) {
                    return "huge";
                } else {
                    return "positive";
                }
            } else {
                if (n == 0) {
                    return "zero";
                } else {
                    return "negative";
                }
            }
        };
        print(classify(500));
        print(classify(42));
        print(classify(0));
        print(classify(-3));
        """
        ev = run(source)
        assert ev.output == ["huge", "positive", "zero", "negative"]

    def test_escape_in_print(self):
        """String with escaped quotes used in print."""
        source = r'''
        let msg = "He said \"hi\"";
        print(msg);
        '''
        ev = run(source)
        assert ev.output == ['He said "hi"']

    def test_complex_program(self):
        """Full program exercising many features."""
        source = """
        let sum_range = fn(start, end) {
            let total = 0;
            let i = start;
            while (i <= end) {
                total = total + i;
                i = i + 1;
            }
            return total;
        };
        print(sum_range(1, 10));

        let map_fn = fn(f, n) {
            return f(n);
        };
        let square = fn(x) { return x * x; };
        print(map_fn(square, 7));
        """
        ev = run(source)
        assert ev.output == ["55", "49"]

    def test_break_continue_mixed(self):
        """Nested loops with both break and continue."""
        source = """
        let result = 0;
        let i = 0;
        while (i < 5) {
            i = i + 1;
            if (i == 3) { continue; }
            let j = 0;
            while (j < 10) {
                j = j + 1;
                if (j > 2) { break; }
            }
            result = result + i * 10 + j;
        }
        print(result);
        """
        # i=1: j breaks at 3 -> 13
        # i=2: j breaks at 3 -> 23
        # i=3: continue (skip)
        # i=4: j breaks at 3 -> 43
        # i=5: j breaks at 3 -> 53
        # total = 13+23+43+53 = 132
        ev = run(source)
        assert ev.output == ["132"]


# ═══════════════════════════════════════════════════════════
#  ERROR HANDLING TESTS
# ═══════════════════════════════════════════════════════════

class TestErrors:
    def test_undefined_variable(self):
        with pytest.raises(NameError):
            run("print(x);")

    def test_division_by_zero(self):
        with pytest.raises(ZeroDivisionError):
            run("let x = 10 / 0;")

    def test_not_a_function(self):
        with pytest.raises(TypeError):
            run("let x = 5; x(1);")

    def test_syntax_error(self):
        with pytest.raises(SyntaxError):
            run("let = ;")

    def test_unexpected_char(self):
        with pytest.raises(SyntaxError):
            run("let x = @;")
