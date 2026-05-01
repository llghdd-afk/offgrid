# 表达式计算器 — 支持 +, -, *, /, 括号, 负数, 变量
# 有人报告了一些计算结果不对，请找出并修复所有 bug，让测试全部通过

class Calculator:
    def __init__(self):
        self.variables = {}

    def set_var(self, name: str, value: float):
        self.variables[name] = value

    def evaluate(self, expr: str) -> float:
        """计算表达式，支持 +, -, *, /, 括号, 变量引用"""
        tokens = self._tokenize(expr)
        pos = [0]
        result = self._parse_expr(tokens, pos)
        return result

    def _tokenize(self, expr: str) -> list:
        tokens = []
        i = 0
        while i < len(expr):
            c = expr[i]
            if c.isspace():
                i += 1
                continue
            if c in '+-*/()':
                tokens.append(c)
                i += 1
            elif c.isdigit() or c == '.':
                j = i
                while j < len(expr) and (expr[j].isdigit() or expr[j] == '.'):
                    j += 1
                tokens.append(float(expr[i:j]))
                i = j
            elif c.isalpha() or c == '_':
                j = i
                while j < len(expr) and (expr[j].isalnum() or expr[j] == '_'):
                    j += 1
                name = expr[i:j]
                if name in self.variables:
                    tokens.append(self.variables[name])
                else:
                    raise NameError(f"Undefined variable: {name}")
                i = j
            else:
                raise SyntaxError(f"Unexpected character: {c}")
        return tokens

    def _parse_expr(self, tokens, pos) -> float:
        """expr = term (('+' | '-') term)*"""
        left = self._parse_term(tokens, pos)
        while pos[0] < len(tokens) and tokens[pos[0]] in ('+', '-'):
            op = tokens[pos[0]]
            pos[0] += 1
            right = self._parse_term(tokens, pos)
            if op == '+':
                left += right
            else:
                left -= right
        return left

    def _parse_term(self, tokens, pos) -> float:
        """term = factor (('*' | '/') factor)*"""
        left = self._parse_factor(tokens, pos)
        while pos[0] < len(tokens) and tokens[pos[0]] in ('*', '/'):
            op = tokens[pos[0]]
            pos[0] += 1
            right = self._parse_factor(tokens, pos)
            if op == '*':
                left *= right
            else:
                left = left / right
        return left

    def _parse_factor(self, tokens, pos) -> float:
        """factor = NUMBER | '(' expr ')' | unary_minus"""
        if pos[0] >= len(tokens):
            raise SyntaxError("Unexpected end of expression")

        token = tokens[pos[0]]

        if token == '(':
            pos[0] += 1
            result = self._parse_expr(tokens, pos)
            if pos[0] >= len(tokens) or tokens[pos[0]] != ')':
                raise SyntaxError("Missing closing parenthesis")
            pos[0] += 1
            return result
        elif token == '-':
            pos[0] += 1
            return self._parse_factor(tokens, pos)
        elif isinstance(token, (int, float)):
            pos[0] += 1
            return token
        else:
            raise SyntaxError(f"Unexpected token: {token}")
