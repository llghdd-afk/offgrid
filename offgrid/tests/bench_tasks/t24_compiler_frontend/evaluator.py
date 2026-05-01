"""Mini-language evaluator: tree-walking interpreter with environments."""

from typing import Any, Dict, List, Optional
from parser import (
    NumberLit, StringLit, BoolLit, Ident, BinaryOp, UnaryOp,
    LetStmt, AssignStmt, IfStmt, WhileStmt, FnDef, FnCall,
    PrintStmt, ReturnStmt, BreakStmt, ContinueStmt, Block,
)


# ── Control flow exceptions ───────────────────────────────

class ReturnException(Exception):
    def __init__(self, value):
        self.value = value

class BreakException(Exception):
    pass

class ContinueException(Exception):
    pass


# ── Environment (scope chain) ─────────────────────────────

class Environment:
    def __init__(self, parent: Optional["Environment"] = None):
        self.store: Dict[str, Any] = {}
        self.parent = parent

    def get(self, name: str) -> Any:
        if name in self.store:
            return self.store[name]
        if self.parent is not None:
            root = self.parent
            while root.parent is not None:
                root = root.parent
            if name in root.store:
                return root.store[name]
        raise NameError(f"Undefined variable: {name}")

    def set(self, name: str, value: Any):
        """Set variable in the scope where it is defined (for assignment)."""
        if name in self.store:
            self.store[name] = value
            return
        if self.parent is not None:
            self.parent.set(name, value)
            return
        raise NameError(f"Undefined variable: {name}")

    def define(self, name: str, value: Any):
        """Define a new variable in the current scope."""
        self.store[name] = value


# ── Closure ────────────────────────────────────────────────

class Closure:
    def __init__(self, params: List[str], body: Block, env: Environment):
        self.params = params
        self.body = body
        self.env = env


# ── Evaluator ──────────────────────────────────────────────

class Evaluator:
    def __init__(self):
        self.output: List[str] = []  # captured print output

    def run(self, program: Block) -> Any:
        env = Environment()
        return self.eval_block(program, env)

    def eval_block(self, block: Block, env: Environment) -> Any:
        result = None
        for stmt in block.statements:
            result = self.eval_node(stmt, env)
        return result

    def eval_node(self, node, env: Environment) -> Any:
        # ── Literals ──
        if isinstance(node, NumberLit):
            return node.value
        if isinstance(node, StringLit):
            return node.value
        if isinstance(node, BoolLit):
            return node.value

        # ── Identifier ──
        if isinstance(node, Ident):
            return env.get(node.name)

        # ── Binary operators ──
        if isinstance(node, BinaryOp):
            left = self.eval_node(node.left, env)
            right = self.eval_node(node.right, env)
            return self._eval_binop(node.op, left, right)

        # ── Unary operators ──
        if isinstance(node, UnaryOp):
            operand = self.eval_node(node.operand, env)
            if node.op == "-":
                return -operand
            if node.op == "!":
                return not self._truthy(operand)

        # ── Let statement ──
        if isinstance(node, LetStmt):
            val = self.eval_node(node.value, env)
            env.define(node.name, val)
            return val

        # ── Assignment ──
        if isinstance(node, AssignStmt):
            val = self.eval_node(node.value, env)
            env.set(node.name, val)
            return val

        # ── If statement ──
        if isinstance(node, IfStmt):
            cond = self.eval_node(node.condition, env)
            if self._truthy(cond):
                return self.eval_block(node.consequence, env)
            elif node.alternative:
                return self.eval_block(node.alternative, env)
            return None

        # ── While statement ──
        if isinstance(node, WhileStmt):
            result = None
            while self._truthy(self.eval_node(node.condition, env)):
                try:
                    result = self.eval_block(node.body, env)
                except ContinueException:
                    continue
            return result

        # ── Function definition ──
        if isinstance(node, FnDef):
            return Closure(node.params, node.body, env)

        # ── Function call ──
        if isinstance(node, FnCall):
            func = self.eval_node(node.function, env)
            if not isinstance(func, Closure):
                raise TypeError(f"Not a function: {func}")
            if len(func.params) != len(node.args):
                raise TypeError(
                    f"Expected {len(func.params)} args, got {len(node.args)}"
                )
            args = [self.eval_node(a, env) for a in node.args]
            for p, a in zip(func.params, args):
                func.env.define(p, a)
            try:
                return self.eval_block(func.body, func.env)
            except ReturnException as ret:
                return ret.value

        # ── Print ──
        if isinstance(node, PrintStmt):
            val = self.eval_node(node.value, env)
            self.output.append(str(val))
            return val

        # ── Return ──
        if isinstance(node, ReturnStmt):
            val = self.eval_node(node.value, env)
            raise ReturnException(val)

        # ── Break / Continue ──
        if isinstance(node, BreakStmt):
            raise BreakException()
        if isinstance(node, ContinueStmt):
            raise ContinueException()

        # ── Block ──
        if isinstance(node, Block):
            return self.eval_block(node, env)

        raise RuntimeError(f"Unknown node type: {type(node).__name__}")

    def _eval_binop(self, op: str, left, right):
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            if right == 0:
                raise ZeroDivisionError("Division by zero")
            return left // right if isinstance(left, int) and isinstance(right, int) else left / right
        if op == "%":
            return left % right
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "<":
            return left < right
        if op == ">":
            return left > right
        if op == "<=":
            return left <= right
        if op == ">=":
            return left >= right
        if op == "&&":
            return left and right
        if op == "||":
            return left or right
        raise RuntimeError(f"Unknown operator: {op}")

    def _truthy(self, value) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            return len(value) > 0
        return True
