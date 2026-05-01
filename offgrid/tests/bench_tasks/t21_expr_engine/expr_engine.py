# expr_engine.py — 支持变量绑定和惰性求值的表达式引擎
# 用户报告在涉及闭包、短路求值和递归深度场景下出现异常结果
# 请阅读代码和测试，找出所有 bug 并修复，让全部测试通过。不要修改测试文件。

from abc import ABC, abstractmethod

_eval_cache: dict[tuple, object] = {}
_eval_depth = 0
MAX_EVAL_DEPTH = 200

_UNINITIALIZED = object()  # sentinel for letrec-style bindings


class Environment:
    """Variable environment with lexical scoping."""

    def __init__(self, bindings: dict = None, parent: "Environment" = None):
        self.bindings = dict(bindings) if bindings else {}
        self.parent = parent

    def lookup(self, name: str):
        if name in self.bindings:
            val = self.bindings[name]
            if val is _UNINITIALIZED:
                raise NameError(f"Variable used before initialization: {name}")
            return val
        if self.parent is not None:
            return self.parent.lookup(name)
        raise NameError(f"Undefined variable: {name}")

    def extend(self, name: str, value) -> "Environment":
        """Create a child environment with one new binding."""
        return Environment({name: value}, parent=self)

    def set(self, name: str, value):
        """Mutate current environment by adding/updating a binding."""
        self.bindings[name] = value

    def snapshot(self) -> "Environment":
        """Create a shallow copy of this environment (same parent chain)."""
        return Environment(dict(self.bindings), parent=self.parent)

    def fingerprint(self) -> tuple:
        """Return a hashable representation of the full environment chain."""
        parts = []
        env = self
        while env is not None:
            items = []
            for k, v in sorted(env.bindings.items()):
                try:
                    hash(v)
                    items.append((k, v))
                except TypeError:
                    items.append((k, id(v)))
            parts.append(tuple(items))
            env = env.parent
        return tuple(parts)


class Expr(ABC):
    """Abstract base class for all expression nodes."""

    _id_counter = 0

    def __init__(self):
        Expr._id_counter += 1
        self._id = Expr._id_counter

    @abstractmethod
    def evaluate(self, env: Environment):
        ...

    def _cache_key(self, env: Environment) -> tuple:
        """Generate a cache key for memoization of expression results."""
        return (self._id,)


class Literal(Expr):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def evaluate(self, env: Environment):
        return self.value

    def __repr__(self):
        return f"Literal({self.value!r})"


class Variable(Expr):
    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def evaluate(self, env: Environment):
        key = self._cache_key(env)
        if key in _eval_cache:
            return _eval_cache[key]
        result = env.lookup(self.name)
        _eval_cache[key] = result
        return result

    def __repr__(self):
        return f"Variable({self.name!r})"


class BinaryOp(Expr):
    OPERATORS = {
        '+': lambda a, b: a + b,
        '-': lambda a, b: a - b,
        '*': lambda a, b: a * b,
        '/': lambda a, b: a // b,
        '==': lambda a, b: a == b,
        '!=': lambda a, b: a != b,
        '<': lambda a, b: a < b,
        '>': lambda a, b: a > b,
        'and': lambda a, b: a and b,
        'or': lambda a, b: a or b,
    }

    def __init__(self, op: str, left: Expr, right: Expr):
        super().__init__()
        if op not in self.OPERATORS:
            raise ValueError(f"Unknown operator: {op}")
        self.op = op
        self.left = left
        self.right = right

    def evaluate(self, env: Environment):
        global _eval_depth
        _eval_depth += 1
        try:
            left_val = self.left.evaluate(env)
            right_val = self.right.evaluate(env)
            fn = self.OPERATORS[self.op]
            return fn(left_val, right_val)
        finally:
            _eval_depth -= 1

    def __repr__(self):
        return f"BinaryOp({self.op!r}, {self.left!r}, {self.right!r})"


class IfExpr(Expr):
    def __init__(self, condition: Expr, then_branch: Expr, else_branch: Expr):
        super().__init__()
        self.condition = condition
        self.then_branch = then_branch
        self.else_branch = else_branch

    def evaluate(self, env: Environment):
        cond = self.condition.evaluate(env)
        if cond:
            return self.then_branch.evaluate(env)
        else:
            return self.else_branch.evaluate(env)


class LetExpr(Expr):
    """let name = value_expr in body_expr

    Uses letrec semantics to support recursive function definitions:
    the value expression is evaluated in an environment that already
    contains a slot for the binding (initially uninitialized), so
    lambdas can capture a reference to themselves.
    """

    def __init__(self, name: str, value_expr: Expr, body_expr: Expr):
        super().__init__()
        self.name = name
        self.value_expr = value_expr
        self.body_expr = body_expr

    def evaluate(self, env: Environment):
        # Create a new scope with a placeholder, evaluate, then fill it in.
        new_env = env.extend(self.name, _UNINITIALIZED)
        val = self.value_expr.evaluate(new_env)
        new_env.set(self.name, val)
        env.set(self.name, val)
        return self.body_expr.evaluate(new_env)


class Closure:
    """Runtime representation of a function (lambda + captured environment)."""

    def __init__(self, param: str, body: Expr, env: Environment):
        self.param = param
        self.body = body
        self.env = env

    def __repr__(self):
        return f"Closure({self.param}, {self.body!r})"


class Lambda(Expr):
    def __init__(self, param: str, body: Expr):
        super().__init__()
        self.param = param
        self.body = body

    def evaluate(self, env: Environment):
        return Closure(self.param, self.body, env)

    def __repr__(self):
        return f"Lambda({self.param!r}, {self.body!r})"


class Apply(Expr):
    def __init__(self, func_expr: Expr, arg_expr: Expr):
        super().__init__()
        self.func_expr = func_expr
        self.arg_expr = arg_expr

    def evaluate(self, env: Environment):
        global _eval_depth
        _eval_depth += 1
        try:
            func = self.func_expr.evaluate(env)
            if not isinstance(func, Closure):
                raise TypeError(f"Cannot apply non-function: {func!r}")
            arg_val = self.arg_expr.evaluate(env)
            call_env = func.env.extend(func.param, arg_val)
            return func.body.evaluate(call_env)
        finally:
            _eval_depth -= 1


def clear_cache():
    """Clear the expression evaluation cache."""
    _eval_cache.clear()


def reset_depth():
    """Reset the evaluation depth counter."""
    global _eval_depth
    _eval_depth = 0
