"""Token definitions for the AUJava lexer.

A *token* is the smallest meaningful unit of source code -- a keyword, an
identifier, an integer literal, or a piece of punctuation/operator. The lexer
turns the raw source text into a flat list of these.

Every token remembers where it came from (`line`, `column`) so that later
stages (parser, semantic analyzer) can produce precise error messages.
"""

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    # --- literals & names ---
    IDENT = auto()        # myVar, Student, foo
    INT = auto()          # 42, 0, 100

    # --- keywords ---
    CLASS = auto()
    EXTENDS = auto()
    PUBLIC = auto()
    STATIC = auto()
    VOID = auto()
    INT_TYPE = auto()     # the word "int"
    BOOLEAN = auto()      # the word "boolean"
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    BREAK = auto()
    CONTINUE = auto()
    RETURN = auto()
    NEW = auto()
    THIS = auto()
    TRUE = auto()
    FALSE = auto()

    # --- arithmetic operators ---
    PLUS = auto()         # +
    MINUS = auto()        # -
    STAR = auto()         # *
    SLASH = auto()        # /
    PERCENT = auto()      # %

    # --- assignment ---
    ASSIGN = auto()       # =

    # --- comparison operators ---
    EQ = auto()           # ==
    NEQ = auto()          # !=
    LT = auto()           # <
    GT = auto()           # >
    LE = auto()           # <=
    GE = auto()           # >=

    # --- boolean operators ---
    AND = auto()          # &&
    OR = auto()           # ||
    NOT = auto()          # !

    # --- punctuation ---
    DOT = auto()          # .
    COMMA = auto()        # ,
    SEMICOLON = auto()    # ;
    LPAREN = auto()       # (
    RPAREN = auto()       # )
    LBRACE = auto()       # {
    RBRACE = auto()       # }
    LBRACKET = auto()     # [
    RBRACKET = auto()     # ]

    # --- end of input ---
    EOF = auto()


# Reserved words: any identifier-looking text that matches one of these is a
# keyword, not a plain identifier. Note that `String`, `System`, `out`, and
# `println` are intentionally NOT keywords -- they are treated as ordinary
# identifiers and recognized structurally by the parser (e.g. the special
# `System.out.println(...)` statement and the `String[] args` main signature).
KEYWORDS = {
    "class": TokenType.CLASS,
    "extends": TokenType.EXTENDS,
    "public": TokenType.PUBLIC,
    "static": TokenType.STATIC,
    "void": TokenType.VOID,
    "int": TokenType.INT_TYPE,
    "boolean": TokenType.BOOLEAN,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "break": TokenType.BREAK,
    "continue": TokenType.CONTINUE,
    "return": TokenType.RETURN,
    "new": TokenType.NEW,
    "this": TokenType.THIS,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
}


@dataclass
class Token:
    type: TokenType
    value: str        # the exact text, e.g. "class", "42", "=="
    line: int         # 1-based line number
    column: int       # 1-based column of the token's first character

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.column})"
