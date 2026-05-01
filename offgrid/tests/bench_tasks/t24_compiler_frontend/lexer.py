"""Mini-language lexer: tokenizes source code into a list of tokens."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import List


class TokenType(Enum):
    NUMBER = auto()
    STRING = auto()
    IDENT = auto()
    KEYWORD = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EQ = auto()        # =
    EQEQ = auto()      # ==
    NEQ = auto()        # !=
    LT = auto()
    GT = auto()
    LTE = auto()        # <=
    GTE = auto()        # >=
    BANG = auto()        # !
    AND = auto()         # &&
    OR = auto()          # ||
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    COMMA = auto()
    SEMICOLON = auto()
    EOF = auto()


KEYWORDS = {"let", "fn", "if", "else", "while", "return", "print", "true", "false", "break", "continue"}


@dataclass
class Token:
    type: TokenType
    value: str
    line: int = 0

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r})"


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1

    def tokenize(self) -> List[Token]:
        tokens = []
        while self.pos < len(self.source):
            ch = self.source[self.pos]

            # whitespace
            if ch in " \t\r":
                self.pos += 1
                continue
            if ch == "\n":
                self.line += 1
                self.pos += 1
                continue

            # single-line comment
            if ch == "/" and self.pos + 1 < len(self.source) and self.source[self.pos + 1] == "/":
                while self.pos < len(self.source) and self.source[self.pos] != "\n":
                    self.pos += 1
                continue

            # number
            if ch.isdigit():
                start = self.pos
                while self.pos < len(self.source) and self.source[self.pos].isdigit():
                    self.pos += 1
                tokens.append(Token(TokenType.NUMBER, self.source[start:self.pos], self.line))
                continue

            # string literal
            if ch == '"':
                self.pos += 1  # skip opening quote
                result = []
                while self.pos < len(self.source):
                    c = self.source[self.pos]
                    if c == '"':
                        break
                    if c == "\\":
                        self.pos += 1
                        if self.pos < len(self.source):
                            esc = self.source[self.pos]
                            if esc == "n":
                                result.append("\n")
                            elif esc == "t":
                                result.append("\t")
                            elif esc == "\\":
                                result.append("\\")
                            elif esc == '"':
                                pass
                            else:
                                result.append(esc)
                    else:
                        result.append(c)
                    self.pos += 1
                self.pos += 1  # skip closing quote
                tokens.append(Token(TokenType.STRING, "".join(result), self.line))
                continue

            # identifier / keyword
            if ch.isalpha() or ch == "_":
                start = self.pos
                while self.pos < len(self.source) and (self.source[self.pos].isalnum() or self.source[self.pos] == "_"):
                    self.pos += 1
                word = self.source[start:self.pos]
                if word in KEYWORDS:
                    tokens.append(Token(TokenType.KEYWORD, word, self.line))
                else:
                    tokens.append(Token(TokenType.IDENT, word, self.line))
                continue

            # two-char operators
            two = self.source[self.pos:self.pos + 2]
            if two == "==":
                tokens.append(Token(TokenType.EQEQ, "==", self.line)); self.pos += 2; continue
            if two == "!=":
                tokens.append(Token(TokenType.NEQ, "!=", self.line)); self.pos += 2; continue
            if two == "<=":
                tokens.append(Token(TokenType.LTE, "<=", self.line)); self.pos += 2; continue
            if two == ">=":
                tokens.append(Token(TokenType.GTE, ">=", self.line)); self.pos += 2; continue
            if two == "&&":
                tokens.append(Token(TokenType.AND, "&&", self.line)); self.pos += 2; continue
            if two == "||":
                tokens.append(Token(TokenType.OR, "||", self.line)); self.pos += 2; continue

            # single-char operators and delimiters
            single_map = {
                "+": TokenType.PLUS, "-": TokenType.MINUS, "*": TokenType.STAR,
                "/": TokenType.SLASH, "%": TokenType.PERCENT, "=": TokenType.EQ,
                "<": TokenType.LT, ">": TokenType.GT, "!": TokenType.BANG,
                "(": TokenType.LPAREN, ")": TokenType.RPAREN,
                "{": TokenType.LBRACE, "}": TokenType.RBRACE,
                ",": TokenType.COMMA, ";": TokenType.SEMICOLON,
            }
            if ch in single_map:
                tokens.append(Token(single_map[ch], ch, self.line))
                self.pos += 1
                continue

            raise SyntaxError(f"Unexpected character {ch!r} at line {self.line}")

        tokens.append(Token(TokenType.EOF, "", self.line))
        return tokens
