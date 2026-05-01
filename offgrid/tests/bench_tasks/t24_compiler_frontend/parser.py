"""Mini-language parser: recursive descent parser producing AST nodes."""

from dataclasses import dataclass, field
from typing import List, Optional, Any
from lexer import Token, TokenType


# ── AST Nodes ──────────────────────────────────────────────

@dataclass
class NumberLit:
    value: int

@dataclass
class StringLit:
    value: str

@dataclass
class BoolLit:
    value: bool

@dataclass
class Ident:
    name: str

@dataclass
class BinaryOp:
    op: str
    left: Any
    right: Any

@dataclass
class UnaryOp:
    op: str
    operand: Any

@dataclass
class LetStmt:
    name: str
    value: Any

@dataclass
class AssignStmt:
    name: str
    value: Any

@dataclass
class IfStmt:
    condition: Any
    consequence: Any
    alternative: Any = None

@dataclass
class WhileStmt:
    condition: Any
    body: Any

@dataclass
class FnDef:
    params: List[str]
    body: Any

@dataclass
class FnCall:
    function: Any
    args: List[Any]

@dataclass
class PrintStmt:
    value: Any

@dataclass
class ReturnStmt:
    value: Any

@dataclass
class BreakStmt:
    pass

@dataclass
class ContinueStmt:
    pass

@dataclass
class Block:
    statements: List[Any]


# ── Parser ─────────────────────────────────────────────────

class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, ttype: TokenType, value: str = None) -> Token:
        tok = self.advance()
        if tok.type != ttype:
            raise SyntaxError(f"Expected {ttype}, got {tok}")
        if value is not None and tok.value != value:
            raise SyntaxError(f"Expected {value!r}, got {tok.value!r}")
        return tok

    def parse(self) -> Block:
        stmts = []
        while self.peek().type != TokenType.EOF:
            stmts.append(self.parse_statement())
        return Block(stmts)

    def parse_statement(self):
        tok = self.peek()

        if tok.type == TokenType.KEYWORD and tok.value == "let":
            return self.parse_let()
        if tok.type == TokenType.KEYWORD and tok.value == "if":
            return self.parse_if()
        if tok.type == TokenType.KEYWORD and tok.value == "while":
            return self.parse_while()
        if tok.type == TokenType.KEYWORD and tok.value == "return":
            return self.parse_return()
        if tok.type == TokenType.KEYWORD and tok.value == "print":
            return self.parse_print()
        if tok.type == TokenType.KEYWORD and tok.value == "break":
            self.advance()
            self.expect(TokenType.SEMICOLON)
            return BreakStmt()
        if tok.type == TokenType.KEYWORD and tok.value == "continue":
            self.advance()
            self.expect(TokenType.SEMICOLON)
            return ContinueStmt()

        # assignment or expression statement
        expr = self.parse_expression()
        if isinstance(expr, Ident) and self.peek().type == TokenType.EQ:
            self.advance()  # consume =
            val = self.parse_expression()
            self.expect(TokenType.SEMICOLON)
            return AssignStmt(expr.name, val)
        self.expect(TokenType.SEMICOLON)
        return expr

    def parse_let(self):
        self.advance()  # consume 'let'
        name = self.expect(TokenType.IDENT).value
        self.expect(TokenType.EQ)
        value = self.parse_expression()
        self.expect(TokenType.SEMICOLON)
        return LetStmt(name, value)

    def parse_if(self):
        self.advance()  # consume 'if'
        self.expect(TokenType.LPAREN)
        cond = self.parse_expression()
        self.expect(TokenType.RPAREN)
        cons = self.parse_block()
        alt = None
        if self.peek().type == TokenType.KEYWORD and self.peek().value == "else":
            self.advance()
            alt = self.parse_block()
        return IfStmt(cond, cons, alt)

    def parse_while(self):
        self.advance()  # consume 'while'
        self.expect(TokenType.LPAREN)
        cond = self.parse_expression()
        self.expect(TokenType.RPAREN)
        body = self.parse_block()
        return WhileStmt(cond, body)

    def parse_return(self):
        self.advance()  # consume 'return'
        value = self.parse_expression()
        self.expect(TokenType.SEMICOLON)
        return ReturnStmt(value)

    def parse_print(self):
        self.advance()  # consume 'print'
        self.expect(TokenType.LPAREN)
        value = self.parse_expression()
        self.expect(TokenType.RPAREN)
        self.expect(TokenType.SEMICOLON)
        return PrintStmt(value)

    def parse_block(self) -> Block:
        self.expect(TokenType.LBRACE)
        stmts = []
        while self.peek().type != TokenType.RBRACE:
            stmts.append(self.parse_statement())
        self.expect(TokenType.RBRACE)
        return Block(stmts)

    # ── Expression parsing (precedence climbing) ───────────

    def parse_expression(self):
        return self.parse_or()

    def parse_or(self):
        left = self.parse_and()
        while self.peek().type == TokenType.OR:
            self.advance()
            right = self.parse_and()
            left = BinaryOp("||", left, right)
        return left

    def parse_and(self):
        left = self.parse_equality()
        while self.peek().type == TokenType.AND:
            self.advance()
            right = self.parse_equality()
            left = BinaryOp("&&", left, right)
        return left

    def parse_equality(self):
        left = self.parse_comparison()
        while self.peek().type in (TokenType.EQEQ, TokenType.NEQ):
            op = self.advance().value
            right = self.parse_comparison()
            left = BinaryOp(op, left, right)
        return left

    def parse_comparison(self):
        left = self.parse_additive()
        while self.peek().type in (TokenType.LT, TokenType.GT, TokenType.LTE, TokenType.GTE):
            op = self.advance().value
            right = self.parse_additive()
            left = BinaryOp(op, left, right)
        return left

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self.peek().type in (TokenType.PLUS, TokenType.MINUS):
            op = self.advance().value
            right = self.parse_multiplicative()
            left = BinaryOp(op, left, right)
        return left

    def parse_multiplicative(self):
        left = self.parse_unary()
        while self.peek().type in (TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op = self.advance().value
            right = self.parse_unary()
            left = BinaryOp(op, left, right)
        return left

    def parse_unary(self):
        if self.peek().type == TokenType.MINUS:
            self.advance()
            return UnaryOp("-", self.parse_unary())
        if self.peek().type == TokenType.BANG:
            self.advance()
            return UnaryOp("!", self.parse_unary())
        return self.parse_call()

    def parse_call(self):
        expr = self.parse_primary()
        while self.peek().type == TokenType.LPAREN:
            self.advance()
            args = []
            if self.peek().type != TokenType.RPAREN:
                args.append(self.parse_expression())
                while self.peek().type == TokenType.COMMA:
                    self.advance()
                    args.append(self.parse_expression())
            self.expect(TokenType.RPAREN)
            expr = FnCall(expr, args)
        return expr

    def parse_primary(self):
        tok = self.peek()

        if tok.type == TokenType.NUMBER:
            self.advance()
            return NumberLit(int(tok.value))

        if tok.type == TokenType.STRING:
            self.advance()
            return StringLit(tok.value)

        if tok.type == TokenType.KEYWORD and tok.value == "true":
            self.advance()
            return BoolLit(True)

        if tok.type == TokenType.KEYWORD and tok.value == "false":
            self.advance()
            return BoolLit(False)

        if tok.type == TokenType.KEYWORD and tok.value == "fn":
            return self.parse_fn()

        if tok.type == TokenType.IDENT:
            self.advance()
            return Ident(tok.value)

        if tok.type == TokenType.LPAREN:
            self.advance()
            expr = self.parse_expression()
            self.expect(TokenType.RPAREN)
            return expr

        raise SyntaxError(f"Unexpected token {tok}")

    def parse_fn(self):
        self.advance()  # consume 'fn'
        self.expect(TokenType.LPAREN)
        params = []
        if self.peek().type != TokenType.RPAREN:
            params.append(self.expect(TokenType.IDENT).value)
            while self.peek().type == TokenType.COMMA:
                self.advance()
                params.append(self.expect(TokenType.IDENT).value)
        self.expect(TokenType.RPAREN)
        body = self.parse_block()
        return FnDef(params, body)
